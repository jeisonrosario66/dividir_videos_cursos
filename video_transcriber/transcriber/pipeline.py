from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from time import monotonic
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from transcriber.config import Profile, resolve_output_path
from transcriber.srt import write_srt

LOGGER = logging.getLogger(__name__)
DEFAULT_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".m4v")


@dataclass
class TranscriptionSettings:
    input_dir: Path
    output_dir: Path
    language: str | None
    extensions: tuple[str, ...]
    overwrite: bool
    profile: Profile
    model_size: str | None = None
    parallel_files: int | None = None

    @property
    def selected_model(self) -> str:
        return self.model_size or self.profile.model_size

    @property
    def effective_parallel_files(self) -> int:
        if self.parallel_files is None:
            return self.profile.parallel_files
        return max(1, self.parallel_files)


def iter_media_files(root_dir: Path, extensions: tuple[str, ...]) -> Iterable[Path]:
    normalized = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions}
    for path in sorted(root_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in normalized:
            yield path


class TranscriberService:
    def __init__(self, settings: TranscriptionSettings):
        self.settings = settings
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            settings.selected_model,
            device=settings.profile.device,
            compute_type=settings.profile.compute_type,
            cpu_threads=settings.profile.cpu_threads,
            num_workers=max(settings.profile.workers, settings.effective_parallel_files),
        )

    def transcribe_all(self) -> tuple[int, int, int]:
        processed = 0
        skipped = 0
        failed = 0
        pending: list[tuple[Path, Path]] = []
        started_at = monotonic()

        for media_path in iter_media_files(self.settings.input_dir, self.settings.extensions):
            destination = resolve_output_path(
                self.settings.input_dir,
                self.settings.output_dir,
                media_path,
            )

            if destination.exists() and not self.settings.overwrite:
                skipped += 1
                LOGGER.info("Saltando porque ya existe: %s", destination)
                continue

            pending.append((media_path, destination))

        if not pending:
            return processed, skipped, failed

        total = len(pending)
        LOGGER.info(
            "Archivos pendientes=%s | modo=%s | workers=%s | ya_existentes=%s",
            total,
            "paralelo" if self.settings.effective_parallel_files > 1 else "serie",
            self.settings.effective_parallel_files,
            skipped,
        )

        if self.settings.effective_parallel_files == 1:
            for index, (media_path, destination) in enumerate(pending, start=1):
                try:
                    result = self.transcribe_one(media_path, destination)
                    processed += 1
                    self.log_progress(
                        current=index,
                        total=total,
                        processed=processed,
                        failed=failed,
                        skipped=skipped,
                        media_path=media_path,
                        result=result,
                        started_at=started_at,
                    )
                except Exception:
                    failed += 1
                    LOGGER.exception("Fallo transcribiendo %s", media_path)
            return processed, skipped, failed

        with ThreadPoolExecutor(max_workers=self.settings.effective_parallel_files) as executor:
            future_map = {
                executor.submit(self.transcribe_one, media_path, destination): media_path
                for media_path, destination in pending
            }

            completed = 0
            for future in as_completed(future_map):
                media_path = future_map[future]
                completed += 1
                try:
                    result = future.result()
                    processed += 1
                    self.log_progress(
                        current=completed,
                        total=total,
                        processed=processed,
                        failed=failed,
                        skipped=skipped,
                        media_path=media_path,
                        result=result,
                        started_at=started_at,
                    )
                except Exception:
                    failed += 1
                    LOGGER.exception("Fallo transcribiendo %s", media_path)

        return processed, skipped, failed

    def transcribe_one(self, media_path: Path, destination: Path) -> dict[str, str | float]:
        LOGGER.info("Transcribiendo %s", media_path)
        segments, info = self.model.transcribe(
            str(media_path),
            language=self.settings.language,
            beam_size=self.settings.profile.beam_size,
            vad_filter=self.settings.profile.vad_filter,
            task="transcribe",
        )

        serialized_segments = [
            {"start": segment.start, "end": segment.end, "text": segment.text}
            for segment in segments
        ]
        write_srt(serialized_segments, destination)
        return {
            "destination": str(destination),
            "language": info.language,
            "duration": info.duration,
        }

    def log_progress(
        self,
        *,
        current: int,
        total: int,
        processed: int,
        failed: int,
        skipped: int,
        media_path: Path,
        result: dict[str, str | float],
        started_at: float,
    ) -> None:
        percent = (current / total) * 100 if total else 100.0
        elapsed = monotonic() - started_at
        destination = result["destination"]
        language = result["language"]
        duration = result["duration"]
        LOGGER.info(
            "Progreso %s/%s (%.1f%%) | ok=%s | fail=%s | skip=%s | archivo=%s | idioma=%s | duracion=%.2fs | salida=%s | transcurrido=%.1fs",
            current,
            total,
            percent,
            processed,
            failed,
            skipped,
            media_path.name,
            language,
            duration,
            destination,
            elapsed,
        )
