from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_glossary_path() -> Path:
    return (_project_root() / "glossary_bjj.txt").resolve()


def _read_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _read_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() == "true"


def _read_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    input_dir: Path
    output_dir: Path
    work_dir: Path
    overwrite: bool
    chunk_max_chars: int
    max_segments_per_chunk: int
    max_glossary_lines_per_chunk: int
    target_language: str
    glossary_path: Path
    course_context: str
    batch_requests_path: Path
    batch_results_path: Path
    batch_manifest_path: Path


def load_settings() -> Settings:
    project_root = _project_root()
    input_dir = Path(_read_str("INPUT_DIR", str((project_root / "input").resolve()))).expanduser().resolve()
    output_dir = Path(_read_str("OUTPUT_DIR", str((project_root / "output").resolve()))).expanduser().resolve()
    work_dir = Path(_read_str("WORK_DIR", str((project_root / "work").resolve()))).expanduser().resolve()
    batch_requests_path = Path(
        _read_str("BATCH_REQUESTS_PATH", str((work_dir / "openai_batch_requests.jsonl").resolve()))
    ).expanduser().resolve()
    batch_results_path = Path(
        _read_str("BATCH_RESULTS_PATH", str((work_dir / "openai_batch_results.jsonl").resolve()))
    ).expanduser().resolve()
    batch_manifest_path = Path(
        _read_str("BATCH_MANIFEST_PATH", str((work_dir / "translation_manifest.json").resolve()))
    ).expanduser().resolve()

    glossary_path = Path(os.environ.get("GLOSSARY_PATH", str(_default_glossary_path()))).expanduser()
    if not glossary_path.exists():
        glossary_path = _default_glossary_path()

    return Settings(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        input_dir=input_dir,
        output_dir=output_dir,
        work_dir=work_dir,
        overwrite=_read_bool("OVERWRITE", False),
        chunk_max_chars=_read_int("CHUNK_MAX_CHARS", 4500),
        max_segments_per_chunk=_read_int("MAX_SEGMENTS_PER_CHUNK", 80),
        max_glossary_lines_per_chunk=_read_int("MAX_GLOSSARY_LINES_PER_CHUNK", 60),
        target_language=os.environ.get("TARGET_LANGUAGE", "es"),
        glossary_path=glossary_path,
        course_context=os.environ.get(
            "COURSE_CONTEXT",
            "Brazilian Jiu-Jitsu instructional subtitles. Preserve terminology when that reads more naturally than a literal translation.",
        ),
        batch_requests_path=batch_requests_path,
        batch_results_path=batch_results_path,
        batch_manifest_path=batch_manifest_path,
    )
