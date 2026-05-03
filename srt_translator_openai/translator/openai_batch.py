from __future__ import annotations

import json
import logging
from pathlib import Path

from translator.chunking import SubtitleChunk, chunk_entries, file_id_from_path
from translator.config import Settings
from translator.glossary import load_glossary, select_glossary_for_text
from translator.prompts import build_system_prompt, build_user_payload, request_dedup_key, translation_schema
from translator.srt import SubtitleEntry, parse_srt, write_srt

LOGGER = logging.getLogger(__name__)


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _batch_state_path(settings: Settings) -> Path:
    return settings.work_dir / "batch_state.json"


def _load_batch_state(settings: Settings) -> dict:
    return _load_json(_batch_state_path(settings), {})


def _save_batch_state(settings: Settings, payload: dict) -> None:
    _save_json(_batch_state_path(settings), payload)


def _iter_srt_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.srt") if path.is_file())


def _assemble_entries(original_entries: list[SubtitleEntry], translated_by_index: dict[int, str]) -> list[SubtitleEntry]:
    return [
        SubtitleEntry(
            index=entry.index,
            start=entry.start,
            end=entry.end,
            text=translated_by_index.get(entry.index, entry.text),
        )
        for entry in original_entries
    ]


def prepare_batch(settings: Settings) -> int:
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    glossary_lines = load_glossary(settings.glossary_path)
    cache = _load_json(settings.work_dir / "translation_cache.json", {"responses": {}})
    manifest: dict[str, object] = {
        "model": settings.openai_model,
        "system_prompt_version": "bjj-es-v5",
        "files": {},
        "requests": {},
    }

    unique_requests: dict[str, dict[str, object]] = {}
    request_lines: list[str] = []
    total_chunks = 0
    cached_chunks = 0

    for srt_path in _iter_srt_files(settings.input_dir):
        relative_path = srt_path.relative_to(settings.input_dir)
        output_path = settings.output_dir / relative_path
        if output_path.exists() and not settings.overwrite:
            LOGGER.info("SKIP | salida ya existe | %s", relative_path.as_posix())
            continue

        original_entries = parse_srt(srt_path)
        file_id = file_id_from_path(relative_path)
        chunks = chunk_entries(
            file_id=file_id,
            relative_path=relative_path,
            entries=original_entries,
            max_chars=settings.chunk_max_chars,
            max_segments=settings.max_segments_per_chunk,
        )

        file_manifest = {
            "source": str(srt_path),
            "relative_path": relative_path.as_posix(),
            "output": str(output_path),
            "chunks": [],
        }
        manifest["files"][file_id] = file_manifest

        for chunk in chunks:
            total_chunks += 1
            chunk_text = "\n".join(entry.text for entry in chunk.entries)
            filtered_glossary = select_glossary_for_text(
                glossary_lines,
                text=chunk_text,
                max_lines=settings.max_glossary_lines_per_chunk,
            )
            system_prompt = build_system_prompt(
                target_language=settings.target_language,
                course_context=settings.course_context,
                glossary_lines=filtered_glossary,
            )
            user_payload = build_user_payload(chunk)
            dedup_key = request_dedup_key(
                model=settings.openai_model,
                system_prompt=system_prompt,
                user_payload=user_payload,
            )
            file_manifest["chunks"].append(
                {
                    "chunk_id": chunk.chunk_id,
                    "dedup_key": dedup_key,
                    "entry_indexes": [entry.index for entry in chunk.entries],
                }
            )

            if dedup_key in cache["responses"]:
                cached_chunks += 1
                manifest["requests"][dedup_key] = {"status": "cached"}
                continue

            if dedup_key in unique_requests:
                continue

            request_body = {
                "model": settings.openai_model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "text": {"format": translation_schema()},
            }
            unique_requests[dedup_key] = {
                "custom_id": dedup_key,
                "method": "POST",
                "url": "/v1/responses",
                "body": request_body,
            }

    for dedup_key, request in unique_requests.items():
        manifest["requests"][dedup_key] = {"status": "pending"}
        request_lines.append(json.dumps(request, ensure_ascii=False))

    settings.batch_requests_path.parent.mkdir(parents=True, exist_ok=True)
    settings.batch_requests_path.write_text("\n".join(request_lines) + ("\n" if request_lines else ""), encoding="utf-8")
    _save_json(settings.batch_manifest_path, manifest)
    written_from_cache = _write_translated_files(settings=settings, manifest=manifest, cache=cache)

    LOGGER.info(
        "Preparado batch | archivos=%s | chunks=%s | en_cache=%s | requests_nuevos=%s | escritos_cache=%s | jsonl=%s",
        len(manifest["files"]),
        total_chunks,
        cached_chunks,
        len(unique_requests),
        written_from_cache,
        settings.batch_requests_path,
    )
    return 0


def submit_batch(settings: Settings) -> int:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    upload = client.files.create(file=settings.batch_requests_path.open("rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=upload.id,
        endpoint="/v1/responses",
        completion_window="24h",
    )
    state = {
        "batch_id": batch.id,
        "input_file_id": upload.id,
        "status": batch.status,
    }
    _save_batch_state(settings, state)
    LOGGER.info("Batch enviado | batch_id=%s | input_file_id=%s | status=%s", batch.id, upload.id, batch.status)
    return 0


def batch_status(settings: Settings, batch_id: str) -> int:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    batch = client.batches.retrieve(batch_id)
    LOGGER.info(
        "Batch status | id=%s | status=%s | output_file_id=%s | error_file_id=%s",
        batch.id,
        batch.status,
        getattr(batch, "output_file_id", None),
        getattr(batch, "error_file_id", None),
    )
    if getattr(batch, "errors", None):
        LOGGER.error("Batch errors | id=%s | errors=%s", batch.id, batch.errors)
    return 0


def download_error_file(settings: Settings, file_id: str) -> Path:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    file_content = client.files.content(file_id)
    text = file_content.text if hasattr(file_content, "text") else file_content.content.decode("utf-8")
    destination = settings.work_dir / "batch_error.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    LOGGER.error("Error file descargado | file_id=%s | path=%s", file_id, destination)
    return destination


def _extract_output_text(response_body: dict[str, object]) -> str:
    output_text = response_body.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts: list[str] = []
    for item in response_body.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def collect_batch(settings: Settings, batch_id: str) -> int:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    batch = client.batches.retrieve(batch_id)
    if not getattr(batch, "output_file_id", None):
        raise SystemExit(f"El batch {batch_id} todavia no tiene output_file_id. Estado actual: {batch.status}")

    file_content = client.files.content(batch.output_file_id)
    text = file_content.text if hasattr(file_content, "text") else file_content.content.decode("utf-8")
    settings.batch_results_path.parent.mkdir(parents=True, exist_ok=True)
    settings.batch_results_path.write_text(text, encoding="utf-8")

    cache = _load_json(settings.work_dir / "translation_cache.json", {"responses": {}})
    manifest = _load_json(settings.batch_manifest_path, {"files": {}, "requests": {}})

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        row = json.loads(raw_line)
        custom_id = row["custom_id"]
        if row.get("error"):
            manifest["requests"][custom_id] = {"status": "error", "error": row["error"]}
            continue
        body = row["response"]["body"]
        output_json = json.loads(_extract_output_text(body))
        cache["responses"][custom_id] = output_json
        manifest["requests"][custom_id] = {"status": "completed"}

    _save_json(settings.work_dir / "translation_cache.json", cache)
    _save_json(settings.batch_manifest_path, manifest)

    written = _write_translated_files(settings=settings, manifest=manifest, cache=cache)
    LOGGER.info("Batch recolectado | batch_id=%s | archivos_escritos=%s | results=%s", batch_id, written, settings.batch_results_path)
    return 0


def batch_run(settings: Settings, explicit_batch_id: str | None = None) -> int:
    batch_id = explicit_batch_id or _load_batch_state(settings).get("batch_id")

    if not batch_id:
        prepare_batch(settings)
        if not settings.batch_requests_path.exists() or settings.batch_requests_path.stat().st_size == 0:
            LOGGER.info("No hay requests nuevas para enviar. Todo quedo resuelto con cache o archivos existentes.")
            return 0
        return submit_batch(settings)

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    batch = client.batches.retrieve(batch_id)
    _save_batch_state(
        settings,
        {
            "batch_id": batch.id,
            "input_file_id": getattr(batch, "input_file_id", None),
            "output_file_id": getattr(batch, "output_file_id", None),
            "status": batch.status,
        },
    )

    LOGGER.info(
        "Batch auto | id=%s | status=%s | output_file_id=%s",
        batch.id,
        batch.status,
        getattr(batch, "output_file_id", None),
    )
    if getattr(batch, "errors", None):
        LOGGER.error("Batch errors | id=%s | errors=%s", batch.id, batch.errors)

    if batch.status == "completed":
        return collect_batch(settings, batch.id)

    if batch.status in {"failed", "cancelled", "expired"}:
        error_file_id = getattr(batch, "error_file_id", None)
        if error_file_id:
            download_error_file(settings, error_file_id)
        raise SystemExit(
            f"El batch {batch.id} termino en estado {batch.status}. "
            f"{'Se descargo work/batch_error.jsonl para inspeccion.' if error_file_id else 'No se recibio error_file_id desde OpenAI.'} "
            "Si quieres reintentar desde cero, limpia work/batch_state.json y vuelve a ejecutar."
        )

    LOGGER.info("El batch aun no termina. Vuelve a ejecutar el mismo comando mas tarde para recolectar resultados.")
    return 0


def _write_translated_files(*, settings: Settings, manifest: dict, cache: dict) -> int:
    written = 0
    for file_payload in manifest["files"].values():
        source_path = Path(file_payload["source"])
        output_path = Path(file_payload["output"])
        original_entries = parse_srt(source_path)
        translated_by_index: dict[int, str] = {}
        ready = True

        for chunk_payload in file_payload["chunks"]:
            dedup_key = chunk_payload["dedup_key"]
            translated_payload = cache["responses"].get(dedup_key)
            if not translated_payload:
                ready = False
                break
            for item in translated_payload["items"]:
                translated_by_index[int(item["index"])] = item["translated_text"].strip()

        if not ready:
            continue

        translated_entries = _assemble_entries(original_entries, translated_by_index)
        write_srt(output_path, translated_entries)
        written += 1

    return written
