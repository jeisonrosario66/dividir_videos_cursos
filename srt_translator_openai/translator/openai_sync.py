from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from translator.chunking import chunk_entries, file_id_from_path
from translator.config import Settings
from translator.glossary import load_glossary, select_glossary_for_text
from translator.prompts import build_system_prompt, build_user_payload, request_dedup_key, translation_schema
from translator.srt import SubtitleEntry, parse_srt, write_srt

LOGGER = logging.getLogger(__name__)
ENGLISH_MARKERS = {
    "the",
    "and",
    "but",
    "with",
    "from",
    "into",
    "that",
    "this",
    "these",
    "those",
    "then",
    "when",
    "where",
    "your",
    "their",
    "them",
    "they",
    "here",
    "there",
    "inside",
    "outside",
    "control",
    "wrist",
    "hands",
    "lock",
    "double",
    "single",
    "again",
    "start",
    "trying",
    "thinking",
    "down",
    "up",
}
SPANISH_MARKERS = {
    "que",
    "con",
    "para",
    "como",
    "cuando",
    "desde",
    "hacia",
    "aqui",
    "aquí",
    "ellos",
    "ellas",
    "nosotros",
    "nuestra",
    "nuestro",
    "mano",
    "manos",
    "cadera",
    "caderas",
    "agarre",
    "control",
    "muneca",
    "muñeca",
    "encima",
    "debajo",
}
TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚáéíóúÜüÑñ']+")


class ChunkValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkResult:
    translated_map: dict[int, str]
    api_calls: int
    cache_hits: int


@dataclass(frozen=True)
class FileResult:
    relative_path: Path
    translated_chunks: int
    cached_chunks: int


class SharedResponseCache:
    def __init__(self, payload: dict):
        self.payload = payload
        self.lock = threading.Lock()
        self.inflight: dict[str, threading.Event] = {}

    def claim(self, key: str):
        while True:
            with self.lock:
                cached = self.payload["responses"].get(key)
                if cached is not None:
                    return "cached", cached

                event = self.inflight.get(key)
                if event is None:
                    event = threading.Event()
                    self.inflight[key] = event
                    return "owner", event

            event.wait()

    def store(self, key: str, value: dict) -> None:
        with self.lock:
            self.payload["responses"][key] = value

    def discard(self, key: str) -> None:
        with self.lock:
            self.payload["responses"].pop(key, None)

    def release(self, key: str) -> None:
        with self.lock:
            event = self.inflight.pop(key, None)
        if event is not None:
            event.set()


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_srt_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.srt") if path.is_file())


def _extract_output_text(response) -> str:
    if getattr(response, "output_text", None):
        return response.output_text

    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _tokenize_text(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _looks_too_english(source_text: str, translated_text: str) -> bool:
    translated_tokens = _tokenize_text(translated_text)
    if len(translated_tokens) < 6:
        return False

    english_hits = sum(token in ENGLISH_MARKERS for token in translated_tokens)
    spanish_hits = sum(token in SPANISH_MARKERS for token in translated_tokens)
    source_tokens = _tokenize_text(source_text)

    if translated_text.strip() == source_text.strip() and len(translated_text.strip()) >= 20:
        return True

    if english_hits >= 4 and english_hits > spanish_hits + 1:
        return True

    source_token_set = set(source_tokens)
    overlap = sum(token in source_token_set for token in translated_tokens)
    if overlap >= max(6, len(translated_tokens) // 2) and english_hits >= 3 and spanish_hits <= 1:
        return True

    return False


def _validated_translations(chunk, response_json: dict) -> dict[int, str]:
    items = response_json.get("items")
    if not isinstance(items, list):
        raise ChunkValidationError("La respuesta no contiene una lista valida de items.")

    expected_indexes = [entry.index for entry in chunk.entries]
    translated_by_index: dict[int, str] = {}
    suspicious_indexes: list[int] = []

    if len(items) != len(expected_indexes):
        raise ChunkValidationError(
            f"Cantidad de items inesperada. Esperados={len(expected_indexes)} recibidos={len(items)}."
        )

    for entry, item in zip(chunk.entries, items):
        if not isinstance(item, dict):
            raise ChunkValidationError("Uno de los items no es un objeto JSON valido.")

        index = item.get("index")
        translated_text = item.get("translated_text")
        if index != entry.index:
            raise ChunkValidationError(
                f"Indice inesperado en chunk {chunk.chunk_id}. Esperado={entry.index} recibido={index}."
            )
        if not isinstance(translated_text, str) or not translated_text.strip():
            raise ChunkValidationError(f"Texto vacio o invalido para el indice {entry.index}.")

        translated_text = translated_text.strip()
        translated_by_index[entry.index] = translated_text
        if _looks_too_english(entry.text, translated_text):
            suspicious_indexes.append(entry.index)

    if suspicious_indexes:
        raise ChunkValidationError(
            f"Se detecto ingles residual o texto casi sin traducir en indices: {suspicious_indexes[:8]}"
        )

    return translated_by_index


def _translate_chunk_recursive(
    *,
    client,
    settings: Settings,
    course_context: str,
    glossary_lines: list[str],
    chunk,
    cache: SharedResponseCache,
) -> ChunkResult:
    chunk_text = "\n".join(entry.text for entry in chunk.entries)
    filtered_glossary = select_glossary_for_text(
        glossary_lines,
        text=chunk_text,
        max_lines=settings.max_glossary_lines_per_chunk,
    )
    system_prompt = build_system_prompt(
        target_language=settings.target_language,
        course_context=course_context,
        glossary_lines=filtered_glossary,
    )
    payload = build_user_payload(chunk)
    dedup_key = request_dedup_key(
        model=settings.openai_model,
        system_prompt=system_prompt,
        user_payload=payload,
    )

    claimed_kind, claimed_value = cache.claim(dedup_key)
    if claimed_kind == "cached":
        try:
            translated = _validated_translations(chunk, claimed_value)
            return ChunkResult(translated_map=translated, api_calls=0, cache_hits=1)
        except ChunkValidationError:
            cache.discard(dedup_key)
            LOGGER.warning(
                "Cache invalida descartada | archivo=%s | chunk=%s",
                chunk.relative_path,
                chunk.chunk_id,
            )
            return _translate_chunk_recursive(
                client=client,
                settings=settings,
                course_context=course_context,
                glossary_lines=glossary_lines,
                chunk=chunk,
                cache=cache,
            )

    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            text={"format": translation_schema()},
        )
        response_json = json.loads(_extract_output_text(response))
        translated = _validated_translations(chunk, response_json)
        cache.store(dedup_key, response_json)
        return ChunkResult(translated_map=translated, api_calls=1, cache_hits=0)
    except Exception as exc:
        if len(chunk.entries) <= 1:
            raise

        midpoint = max(1, len(chunk.entries) // 2)
        left_entries = chunk.entries[:midpoint]
        right_entries = chunk.entries[midpoint:]
        LOGGER.warning(
            "Chunk grande, conflictivo o mal traducido | archivo=%s | chunk=%s | segmentos=%s | accion=dividir | motivo=%s",
            chunk.relative_path,
            chunk.chunk_id,
            len(chunk.entries),
            exc,
        )

        left_chunk = type(chunk)(
            chunk_id=f"{chunk.chunk_id}__a",
            file_id=chunk.file_id,
            relative_path=chunk.relative_path,
            start_index=left_entries[0].index,
            end_index=left_entries[-1].index,
            entries=list(left_entries),
        )
        right_chunk = type(chunk)(
            chunk_id=f"{chunk.chunk_id}__b",
            file_id=chunk.file_id,
            relative_path=chunk.relative_path,
            start_index=right_entries[0].index,
            end_index=right_entries[-1].index,
            entries=list(right_entries),
        )

        left_result = _translate_chunk_recursive(
            client=client,
            settings=settings,
            course_context=course_context,
            glossary_lines=glossary_lines,
            chunk=left_chunk,
            cache=cache,
        )
        right_result = _translate_chunk_recursive(
            client=client,
            settings=settings,
            course_context=course_context,
            glossary_lines=glossary_lines,
            chunk=right_chunk,
            cache=cache,
        )
        merged = {}
        merged.update(left_result.translated_map)
        merged.update(right_result.translated_map)
        return ChunkResult(
            translated_map=merged,
            api_calls=left_result.api_calls + right_result.api_calls,
            cache_hits=left_result.cache_hits + right_result.cache_hits,
        )
    finally:
        cache.release(dedup_key)


def _translate_one_file(
    *,
    settings: Settings,
    glossary_lines: list[str],
    cache: SharedResponseCache,
    srt_path: Path,
) -> FileResult | None:
    from openai import OpenAI

    relative_path = srt_path.relative_to(settings.input_dir)
    output_path = settings.output_dir / relative_path
    if output_path.exists() and not settings.overwrite:
        LOGGER.info("SKIP | salida ya existe | %s", relative_path.as_posix())
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    entries = parse_srt(srt_path)
    file_id = file_id_from_path(relative_path)
    chunks = chunk_entries(
        file_id=file_id,
        relative_path=relative_path,
        entries=entries,
        max_chars=settings.chunk_max_chars,
        max_segments=settings.max_segments_per_chunk,
    )

    translated_chunks = 0
    cached_chunks = 0
    translated_by_index: dict[int, str] = {}

    for position, chunk in enumerate(chunks, start=1):
        result = _translate_chunk_recursive(
            client=client,
            settings=settings,
            course_context=settings.course_context,
            glossary_lines=glossary_lines,
            chunk=chunk,
            cache=cache,
        )
        translated_chunks += result.api_calls
        cached_chunks += result.cache_hits
        translated_by_index.update(result.translated_map)

        LOGGER.info(
            "OK | archivo=%s | chunk=%s/%s | segmentos=%s | cache=%s",
            relative_path.as_posix(),
            position,
            len(chunks),
            len(chunk.entries),
            "si" if result.api_calls == 0 else "no",
        )

    translated_entries = [
        SubtitleEntry(
            index=entry.index,
            start=entry.start,
            end=entry.end,
            text=translated_by_index.get(entry.index, entry.text),
        )
        for entry in entries
    ]
    write_srt(output_path, translated_entries)
    return FileResult(
        relative_path=relative_path,
        translated_chunks=translated_chunks,
        cached_chunks=cached_chunks,
    )


def translate_sync(settings: Settings) -> int:
    glossary_lines = load_glossary(settings.glossary_path)
    cache_path = settings.work_dir / "translation_cache.json"
    cache = SharedResponseCache(_load_json(cache_path, {"responses": {}}))
    srt_files = _iter_srt_files(settings.input_dir)

    LOGGER.info(
        "Inicio sync | archivos=%s | concurrencia=%s | output=%s",
        len(srt_files),
        settings.sync_concurrency,
        settings.output_dir,
    )

    translated_files = 0
    translated_chunks = 0
    cached_chunks = 0

    with ThreadPoolExecutor(max_workers=settings.sync_concurrency) as executor:
        futures = [
            executor.submit(
                _translate_one_file,
                settings=settings,
                glossary_lines=glossary_lines,
                cache=cache,
                srt_path=srt_path,
            )
            for srt_path in srt_files
        ]

        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            translated_files += 1
            translated_chunks += result.translated_chunks
            cached_chunks += result.cached_chunks

    _save_json(cache_path, cache.payload)
    LOGGER.info(
        "Proceso finalizado | archivos=%s | chunks_api=%s | chunks_cache=%s | concurrencia=%s | output=%s",
        translated_files,
        translated_chunks,
        cached_chunks,
        settings.sync_concurrency,
        settings.output_dir,
    )
    return 0
