from __future__ import annotations

import os
import sys
from pathlib import Path


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


def merge_env_sources(file_values: dict[str, str]) -> dict[str, str]:
    merged = dict(file_values)
    for key in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "INPUT_DIR",
        "OUTPUT_DIR",
        "WORK_DIR",
        "TRANSLATION_MODE",
        "OVERWRITE",
        "SYNC_CONCURRENCY",
        "CHUNK_MAX_CHARS",
        "MAX_SEGMENTS_PER_CHUNK",
        "MAX_GLOSSARY_LINES_PER_CHUNK",
        "TARGET_LANGUAGE",
        "GLOSSARY_PATH",
        "COURSE_CONTEXT",
        "BATCH_REQUESTS_PATH",
        "BATCH_RESULTS_PATH",
        "BATCH_MANIFEST_PATH",
        "BATCH_ID",
    ):
        env_value = os.environ.get(key)
        if env_value is not None and env_value != "":
            merged[key] = env_value
    return merged


def build_default_argv(values: dict[str, str]) -> list[str]:
    mode = values.get("TRANSLATION_MODE", "batch").strip().lower()
    if mode == "sync":
        return ["translate-sync"]
    batch_id = values.get("BATCH_ID", "").strip()
    if batch_id:
        return ["batch-run", "--batch-id", batch_id]
    return ["batch-run"]


if __name__ == "__main__":
    env_path = Path(__file__).with_name(".env")
    values = merge_env_sources(load_env_file(env_path))
    for key, value in values.items():
        os.environ.setdefault(key, value)

    from translator.cli import main

    if len(sys.argv) > 1:
        raise SystemExit(main(sys.argv[1:]))

    raise SystemExit(main(build_default_argv(values)))
