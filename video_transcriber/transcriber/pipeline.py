from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, replace
import logging
from multiprocessing import get_context
from pathlib import Path
from time import monotonic
from typing import Iterable

from transcriber.config import Profile, resolve_output_path
from transcriber.runtime import ensure_cuda_runtime
from transcriber.srt import write_srt

LOGGER = logging.getLogger(__name__)
DEFAULT_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".m4v")
_QUIET_LOGGERS = ("ctranslate2", "faster_whisper", "httpcore", "httpx", "onnxruntime", "urllib3")

_WORKER_MODEL = None
_WORKER_SETTINGS = None


class GpuPoolInitializationError(RuntimeError):
    pass


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
    status_interval_seconds: int = 30

    @property
    def selected_model(self) -> str:
        return self.model_size or self.profile.model_size

    @property
    def effective_parallel_files(self) -> int:
        if self.parallel_files is None:
            return self.profile.parallel_files
        return max(1, self.parallel_files)

    @property
    def execution_mode(self) -> str:
        if self.effective_parallel_files == 1:
            return "serie"
        if self.profile.device == "cuda":
            return "procesos-gpu"
        return "threads"


@dataclass(frozen=True)
class TranscriptionResult:
    destination: str
    language: str
    duration: float


def iter_media_files(root_dir: Path, extensions: tuple[str, ...]) -> Iterable[Path]:
    normalized = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions}
    for path in sorted(root_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in normalized:
            yield path


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _estimated_remaining(elapsed: float, completed: int, total: int) -> float | None:
    if completed <= 0:
        return None
    remaining = max(0, total - completed)
    return (elapsed / completed) * remaining


def _configure_worker_logging() -> None:
    for logger_name in _QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _model_cpu_threads(settings: TranscriptionSettings, *, process_mode: bool) -> int:
    if not process_mode:
        return settings.profile.cpu_threads
    return 1


def _model_num_workers(settings: TranscriptionSettings, *, process_mode: bool) -> int:
    if process_mode:
        return 1
    return max(settings.profile.workers, settings.effective_parallel_files)


def _build_model(settings: TranscriptionSettings, *, process_mode: bool):
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.selected_model,
        device=settings.profile.device,
        compute_type=settings.profile.compute_type,
        cpu_threads=_model_cpu_threads(settings, process_mode=process_mode),
        num_workers=_model_num_workers(settings, process_mode=process_mode),
    )


def _transcribe_with_model(
    model,
    settings: TranscriptionSettings,
    media_path: Path,
    destination: Path,
) -> TranscriptionResult:
    segments, info = model.transcribe(
        str(media_path),
        language=settings.language,
        beam_size=settings.profile.beam_size,
        vad_filter=settings.profile.vad_filter,
        task="transcribe",
    )

    serialized_segments = [
        {"start": segment.start, "end": segment.end, "text": segment.text}
        for segment in segments
    ]
    write_srt(serialized_segments, destination)
    return TranscriptionResult(
        destination=str(destination),
        language=info.language,
        duration=info.duration,
    )


def _worker_initializer(settings: TranscriptionSettings) -> None:
    global _WORKER_MODEL, _WORKER_SETTINGS

    _WORKER_SETTINGS = settings
    _configure_worker_logging()
    ensure_cuda_runtime(settings.profile.device == "cuda", install=False)
    _WORKER_MODEL = _build_model(settings, process_mode=True)


def _worker_transcribe(media_path_str: str, destination_str: str) -> TranscriptionResult:
    if _WORKER_MODEL is None or _WORKER_SETTINGS is None:
        raise RuntimeError("El worker GPU no fue inicializado correctamente.")

    media_path = Path(media_path_str)
    destination = Path(destination_str)
    return _transcribe_with_model(_WORKER_MODEL, _WORKER_SETTINGS, media_path, destination)


class TranscriberService:
    def __init__(self, settings: TranscriptionSettings):
        self.settings = settings
        self.model = None

        if self.settings.execution_mode != "procesos-gpu":
            self.model = _build_model(settings, process_mode=False)

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
                LOGGER.info("SKIP | ya existe | %s", self._display_path(media_path))
                continue

            pending.append((media_path, destination))

        if not pending:
            return processed, skipped, failed

        total = len(pending)
        LOGGER.info(
            "Inicio | archivos=%s | ejecutor=%s | paralelo=%s | modelo=%s | ya_existentes=%s",
            total,
            self.settings.execution_mode,
            self.settings.effective_parallel_files,
            self.settings.selected_model,
            skipped,
        )

        if self.settings.execution_mode == "procesos-gpu":
            return self.transcribe_with_gpu_fallback(
                pending=pending,
                started_at=started_at,
                initial_processed=processed,
                initial_skipped=skipped,
                initial_failed=failed,
            )

        if self.settings.execution_mode == "serie":
            for index, (media_path, destination) in enumerate(pending, start=1):
                try:
                    result = self.transcribe_one(media_path, destination)
                    processed += 1
                    self.log_completion(
                        current=index,
                        total=total,
                        processed=processed,
                        failed=failed,
                        skipped=skipped,
                        pending_count=total - index,
                        media_path=media_path,
                        result=result,
                        started_at=started_at,
                    )
                except Exception as exc:
                    failed += 1
                    self.log_failure(
                        current=index,
                        total=total,
                        processed=processed,
                        failed=failed,
                        skipped=skipped,
                        pending_count=total - index,
                        media_path=media_path,
                        started_at=started_at,
                        error=exc,
                    )
            return processed, skipped, failed

        return self.transcribe_with_executor(
            pending=pending,
            started_at=started_at,
            initial_processed=processed,
            initial_skipped=skipped,
            initial_failed=failed,
            settings=self.settings,
        )

    def transcribe_with_gpu_fallback(
        self,
        *,
        pending: list[tuple[Path, Path]],
        started_at: float,
        initial_processed: int,
        initial_skipped: int,
        initial_failed: int,
    ) -> tuple[int, int, int]:
        requested_parallel = self.settings.effective_parallel_files

        for parallel in range(requested_parallel, 1, -1):
            trial_settings = replace(self.settings, parallel_files=parallel)
            LOGGER.info(
                "Pool GPU | intentando con paralelo=%s | modelo=%s",
                trial_settings.effective_parallel_files,
                trial_settings.selected_model,
            )
            try:
                return self.transcribe_with_executor(
                    pending=pending,
                    started_at=started_at,
                    initial_processed=initial_processed,
                    initial_skipped=initial_skipped,
                    initial_failed=initial_failed,
                    settings=trial_settings,
                )
            except GpuPoolInitializationError:
                next_parallel = parallel - 1
                if next_parallel >= 1:
                    LOGGER.warning(
                        "OOM al inicializar %s modelos en GPU. Reintentando con paralelo=%s.",
                        parallel,
                        next_parallel,
                    )

        LOGGER.warning(
            "La GPU no alcanza para multiproceso con este modelo. Continuando en modo serie sobre una sola instancia del modelo."
        )
        serial_service = TranscriberService(replace(self.settings, parallel_files=1))
        return serial_service.transcribe_all()

    def transcribe_with_executor(
        self,
        *,
        pending: list[tuple[Path, Path]],
        started_at: float,
        initial_processed: int,
        initial_skipped: int,
        initial_failed: int,
        settings: TranscriptionSettings,
    ) -> tuple[int, int, int]:
        processed = initial_processed
        skipped = initial_skipped
        failed = initial_failed
        total = len(pending)

        if settings.execution_mode == "procesos-gpu":
            executor = ProcessPoolExecutor(
                max_workers=settings.effective_parallel_files,
                mp_context=get_context("spawn"),
                initializer=_worker_initializer,
                initargs=(settings,),
            )
        else:
            executor = ThreadPoolExecutor(max_workers=settings.effective_parallel_files)

        with executor:
            future_map = {}
            for media_path, destination in pending:
                if settings.execution_mode == "procesos-gpu":
                    future = executor.submit(_worker_transcribe, str(media_path), str(destination))
                else:
                    future = executor.submit(self.transcribe_one, media_path, destination)
                future_map[future] = media_path

            pending_futures = set(future_map)
            completed = 0

            while pending_futures:
                done, pending_futures = wait(
                    pending_futures,
                    timeout=self.settings.status_interval_seconds,
                    return_when=FIRST_COMPLETED,
                )

                if not done:
                    self.log_status(
                        current=completed,
                        total=total,
                        processed=processed,
                        failed=failed,
                        skipped=skipped,
                        pending_count=len(pending_futures),
                        started_at=started_at,
                        parallel=settings.effective_parallel_files,
                    )
                    continue

                for future in done:
                    media_path = future_map[future]
                    completed += 1
                    pending_count = len(pending_futures)
                    try:
                        result = future.result()
                        processed += 1
                        self.log_completion(
                            current=completed,
                            total=total,
                            processed=processed,
                            failed=failed,
                            skipped=skipped,
                            pending_count=pending_count,
                            media_path=media_path,
                            result=result,
                            started_at=started_at,
                            parallel=settings.effective_parallel_files,
                        )
                    except BrokenProcessPool as exc:
                        raise GpuPoolInitializationError("El pool GPU se rompio al inicializar workers.") from exc
                    except Exception as exc:
                        if (
                            settings.execution_mode == "procesos-gpu"
                            and processed == initial_processed
                            and "terminated abruptly while the future was running or pending" in str(exc)
                        ):
                            raise GpuPoolInitializationError(
                                "Los workers GPU no lograron inicializar el modelo."
                            ) from exc
                        failed += 1
                        self.log_failure(
                            current=completed,
                            total=total,
                            processed=processed,
                            failed=failed,
                            skipped=skipped,
                            pending_count=pending_count,
                            media_path=media_path,
                            started_at=started_at,
                            error=exc,
                            parallel=settings.effective_parallel_files,
                        )

        return processed, skipped, failed

    def transcribe_one(self, media_path: Path, destination: Path) -> TranscriptionResult:
        if self.model is None:
            raise RuntimeError("El modelo no fue inicializado en el proceso principal.")
        return _transcribe_with_model(self.model, self.settings, media_path, destination)

    def _display_path(self, media_path: Path) -> str:
        try:
            return str(media_path.relative_to(self.settings.input_dir))
        except ValueError:
            return media_path.name

    def log_status(
        self,
        *,
        current: int,
        total: int,
        processed: int,
        failed: int,
        skipped: int,
        pending_count: int,
        started_at: float,
        parallel: int,
    ) -> None:
        percent = (current / total) * 100 if total else 100.0
        elapsed = monotonic() - started_at
        eta = _estimated_remaining(elapsed, current, total)
        LOGGER.info(
            "Estado | %s/%s (%.1f%%) | workers=%s | pendientes=%s | ok=%s | fail=%s | skip=%s | transcurrido=%s | eta=%s",
            current,
            total,
            percent,
            parallel,
            pending_count,
            processed,
            failed,
            skipped,
            _format_duration(elapsed),
            _format_duration(eta),
        )

    def log_completion(
        self,
        *,
        current: int,
        total: int,
        processed: int,
        failed: int,
        skipped: int,
        pending_count: int,
        media_path: Path,
        result: TranscriptionResult,
        started_at: float,
        parallel: int,
    ) -> None:
        percent = (current / total) * 100 if total else 100.0
        elapsed = monotonic() - started_at
        eta = _estimated_remaining(elapsed, current, total)
        LOGGER.info(
            "OK     | %s/%s (%.1f%%) | workers=%s | pendientes=%s | ok=%s | fail=%s | skip=%s | archivo=%s | idioma=%s | media=%s | transcurrido=%s | eta=%s",
            current,
            total,
            percent,
            parallel,
            pending_count,
            processed,
            failed,
            skipped,
            self._display_path(media_path),
            result.language,
            _format_duration(result.duration),
            _format_duration(elapsed),
            _format_duration(eta),
        )

    def log_failure(
        self,
        *,
        current: int,
        total: int,
        processed: int,
        failed: int,
        skipped: int,
        pending_count: int,
        media_path: Path,
        started_at: float,
        error: Exception,
        parallel: int,
    ) -> None:
        percent = (current / total) * 100 if total else 100.0
        elapsed = monotonic() - started_at
        eta = _estimated_remaining(elapsed, current, total)
        LOGGER.error(
            "FAIL   | %s/%s (%.1f%%) | workers=%s | pendientes=%s | ok=%s | fail=%s | skip=%s | archivo=%s | error=%s | transcurrido=%s | eta=%s",
            current,
            total,
            percent,
            parallel,
            pending_count,
            processed,
            failed,
            skipped,
            self._display_path(media_path),
            error,
            _format_duration(elapsed),
            _format_duration(eta),
        )
        LOGGER.debug("Traceback detallado para %s", media_path, exc_info=True)
