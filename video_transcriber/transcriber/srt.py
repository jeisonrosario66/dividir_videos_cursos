from __future__ import annotations

from pathlib import Path


def format_timestamp(seconds: float) -> str:
    milliseconds_total = round(seconds * 1000)
    hours = milliseconds_total // 3_600_000
    minutes = (milliseconds_total % 3_600_000) // 60_000
    secs = (milliseconds_total % 60_000) // 1_000
    milliseconds = milliseconds_total % 1_000
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def write_srt(segments: list[dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for index, segment in enumerate(segments, start=1):
            start = format_timestamp(segment["start"])
            end = format_timestamp(segment["end"])
            text = segment["text"].strip()
            handle.write(f"{index}\n{start} --> {end}\n{text}\n\n")
