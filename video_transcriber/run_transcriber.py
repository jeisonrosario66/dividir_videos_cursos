"""Ejecuta la transcripcion leyendo variables desde `.env`.

Pensado para pruebas locales sin repetir un comando largo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from transcriber.runtime import ensure_cuda_runtime


def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def build_argv_from_env(values: dict[str, str]) -> list[str]:
    input_dir = values.get("INPUT_DIR", "").strip()
    if not input_dir:
        raise SystemExit("Define INPUT_DIR en el archivo .env antes de ejecutar este runner.")

    argv = [input_dir]

    output_dir = values.get("OUTPUT_DIR", "").strip()
    if output_dir:
        argv.extend(["-o", output_dir])

    profile = values.get("PROFILE", "").strip()
    if profile:
        argv.extend(["--profile", profile])

    model = values.get("MODEL", "").strip()
    if model:
        argv.extend(["--model", model])

    language = values.get("LANGUAGE", "").strip()
    if language:
        argv.extend(["--language", language])

    if values.get("OVERWRITE", "").strip().lower() == "true":
        argv.append("--overwrite")

    parallel_files = values.get("PARALLEL_FILES", "").strip()
    if parallel_files:
        argv.extend(["--parallel-files", parallel_files])

    status_interval = values.get("STATUS_INTERVAL_SECONDS", "").strip()
    if status_interval:
        argv.extend(["--status-interval", status_interval])

    return argv


def merge_env_sources(file_values: dict[str, str]) -> dict[str, str]:
    merged = dict(file_values)
    for key in (
        "INPUT_DIR",
        "OUTPUT_DIR",
        "PROFILE",
        "MODEL",
        "LANGUAGE",
        "OVERWRITE",
        "PARALLEL_FILES",
        "STATUS_INTERVAL_SECONDS",
    ):
        env_value = os.environ.get(key)
        if env_value is not None and env_value != "":
            merged[key] = env_value
    return merged


if __name__ == "__main__":
    if len(sys.argv) > 1:
        from transcriber.cli import main

        ensure_cuda_runtime(os.environ.get("PROFILE") == "vast")
        raise SystemExit(main(sys.argv[1:]))

    env_path = Path(__file__).with_name(".env")
    values = merge_env_sources(load_env_file(env_path))
    ensure_cuda_runtime(values.get("PROFILE", "").strip() == "vast")

    from transcriber.cli import main

    raise SystemExit(main(build_argv_from_env(values)))
