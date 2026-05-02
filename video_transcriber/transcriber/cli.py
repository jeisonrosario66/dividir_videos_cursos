from __future__ import annotations

import argparse
import logging
from pathlib import Path

from transcriber.config import PROFILES
from transcriber.pipeline import DEFAULT_EXTENSIONS, TranscriberService, TranscriptionSettings
from transcriber.runtime import ensure_cuda_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe videos a subtitulos SRT usando Whisper.",
    )
    parser.add_argument("input_dir", type=Path, help="Carpeta con videos a transcribir.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Carpeta de salida para los .srt. Por defecto crea ../subtitulos desde la carpeta de entrada.",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES.keys()),
        default="local",
        help="Perfil listo para usar segun el entorno.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Sobrescribe el modelo del perfil, por ejemplo: base, small, medium, large-v3.",
    )
    parser.add_argument(
        "--language",
        default="es",
        help="Idioma esperado. Usa auto para deteccion automatica.",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=list(DEFAULT_EXTENSIONS),
        help="Extensiones de video permitidas.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenera archivos .srt aunque ya existan.",
    )
    parser.add_argument(
        "--parallel-files",
        type=int,
        default=None,
        help="Cantidad de archivos a transcribir en paralelo. Si no se indica, usa el valor del perfil.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Nivel de detalle en logs.",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=30,
        help="Segundos entre reportes de estado si no termina ningun archivo.",
    )
    return parser


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    if value.lower() == "auto":
        return None
    return value


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Los logs del modelo y librerias HTTP/ONNX meten mucho ruido durante tandas largas.
    for logger_name in (
        "ctranslate2",
        "faster_whisper",
        "httpcore",
        "httpx",
        "onnxruntime",
        "urllib3",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else (input_dir.parent / "subtitulos").resolve()
    )

    if not input_dir.exists():
        parser.error(f"No existe la ruta de entrada: {input_dir}")
    if not input_dir.is_dir():
        parser.error(f"La ruta de entrada no es una carpeta: {input_dir}")
    if args.parallel_files is not None and args.parallel_files < 1:
        parser.error("--parallel-files debe ser 1 o mayor")
    if args.status_interval < 5:
        parser.error("--status-interval debe ser 5 o mayor")

    profile = PROFILES[args.profile]
    settings = TranscriptionSettings(
        input_dir=input_dir,
        output_dir=output_dir,
        language=normalize_language(args.language),
        extensions=tuple(args.extensions),
        overwrite=args.overwrite,
        profile=profile,
        model_size=args.model,
        parallel_files=args.parallel_files,
        status_interval_seconds=args.status_interval,
    )

    ensure_cuda_runtime(profile.device == "cuda")

    logging.info(
        "Configuracion | perfil=%s | modelo=%s | device=%s | paralelo=%s | estado_cada=%ss | output=%s",
        profile.name,
        settings.selected_model,
        profile.device,
        settings.effective_parallel_files,
        settings.status_interval_seconds,
        output_dir,
    )

    service = TranscriberService(settings)
    processed, skipped, failed = service.transcribe_all()

    logging.info(
        "Proceso finalizado | transcritos=%s | omitidos=%s | fallidos=%s",
        processed,
        skipped,
        failed,
    )
    return 1 if failed else 0
