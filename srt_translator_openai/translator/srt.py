from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SubtitleEntry:
    index: int
    start: str
    end: str
    text: str


def parse_srt(path: Path) -> list[SubtitleEntry]:
    blocks = path.read_text(encoding="utf-8-sig").strip().split("\n\n")
    entries: list[SubtitleEntry] = []
    for block in blocks:
        lines = [line.rstrip("\n") for line in block.splitlines() if line.strip() != ""]
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue
        timing = lines[1]
        if " --> " not in timing:
            continue
        start, end = timing.split(" --> ", 1)
        text = "\n".join(lines[2:]).strip()
        entries.append(SubtitleEntry(index=index, start=start.strip(), end=end.strip(), text=text))
    return entries


def write_srt(path: Path, entries: list[SubtitleEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for entry in entries:
        parts.append(f"{entry.index}\n{entry.start} --> {entry.end}\n{entry.text}".strip())
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
