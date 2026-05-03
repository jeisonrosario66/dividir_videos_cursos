from __future__ import annotations

import argparse
import logging
import os

from translator.config import load_settings
from translator.openai_batch import batch_run, batch_status, collect_batch, prepare_batch, submit_batch
from translator.openai_sync import translate_sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Traduce carpetas de subtitulos .srt al espanol usando OpenAI y contexto BJJ.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    batch_run_parser = subparsers.add_parser(
        "batch-run",
        help="Modo simple para batch: si no hay batch lo prepara y envia; si ya existe lo consulta o recolecta.",
    )
    batch_run_parser.add_argument("--batch-id", default=None, help="ID del batch. Si no se indica, usa BATCH_ID o work/batch_state.json.")
    subparsers.add_parser("prepare-batch", help="Genera manifest y JSONL para Batch API.")
    subparsers.add_parser("submit-batch", help="Sube el JSONL y crea el batch en OpenAI.")
    status_parser = subparsers.add_parser("batch-status", help="Consulta el estado de un batch.")
    status_parser.add_argument("--batch-id", default=None, help="ID del batch. Si no se indica, usa BATCH_ID.")
    collect_parser = subparsers.add_parser("collect-batch", help="Descarga resultados del batch y escribe los .srt traducidos.")
    collect_parser.add_argument("--batch-id", default=None, help="ID del batch. Si no se indica, usa BATCH_ID.")
    subparsers.add_parser("translate-sync", help="Traduce de forma directa, util para pruebas pequenas.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Nivel de detalle en logs.",
    )
    return parser


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )
    for logger_name in ("httpcore", "httpx", "openai", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _resolve_batch_id(explicit_value: str | None) -> str:
    batch_id = explicit_value or os.environ.get("BATCH_ID", "").strip()
    if not batch_id:
        raise SystemExit("Define --batch-id o BATCH_ID para esta operacion.")
    return batch_id


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    settings = load_settings()

    logging.info(
        "Configuracion | comando=%s | modelo=%s | input=%s | output=%s | work=%s",
        args.command,
        settings.openai_model,
        settings.input_dir,
        settings.output_dir,
        settings.work_dir,
    )

    if args.command == "prepare-batch":
        return prepare_batch(settings)
    if args.command == "batch-run":
        return batch_run(settings, getattr(args, "batch_id", None))
    if args.command == "submit-batch":
        return submit_batch(settings)
    if args.command == "batch-status":
        return batch_status(settings, _resolve_batch_id(args.batch_id))
    if args.command == "collect-batch":
        return collect_batch(settings, _resolve_batch_id(args.batch_id))
    if args.command == "translate-sync":
        return translate_sync(settings)

    parser.error(f"Comando no soportado: {args.command}")
