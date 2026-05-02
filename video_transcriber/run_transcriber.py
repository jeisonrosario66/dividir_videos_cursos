"""Ejecuta la transcripcion leyendo variables desde `.env`.

Pensado para pruebas locales sin repetir un comando largo.
"""

from __future__ import annotations

from pathlib import Path

from transcriber.cli import main


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

    return argv


if __name__ == "__main__":
    env_path = Path(__file__).with_name(".env")
    values = load_env_file(env_path)
    raise SystemExit(main(build_argv_from_env(values)))
