from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    name: str
    model_size: str
    device: str
    compute_type: str
    beam_size: int
    vad_filter: bool
    cpu_threads: int
    workers: int
    parallel_files: int


PROFILES = {
    "local": Profile(
        name="local",
        model_size="tiny",
        device="cpu",
        compute_type="int8",
        beam_size=1,
        vad_filter=True,
        cpu_threads=2,
        workers=1,
        parallel_files=1,
    ),
    "vast": Profile(
        name="vast",
        model_size="large-v3",
        device="cuda",
        compute_type="float16",
        beam_size=5,
        vad_filter=True,
        cpu_threads=4,
        workers=2,
        parallel_files=2,
    ),
}


def resolve_output_path(input_root: Path, output_root: Path, media_path: Path) -> Path:
    relative_parent = media_path.parent.relative_to(input_root)
    return output_root / relative_parent / f"{media_path.stem}.srt"
