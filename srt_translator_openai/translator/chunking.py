from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from translator.srt import SubtitleEntry


@dataclass(frozen=True)
class SubtitleChunk:
    chunk_id: str
    file_id: str
    relative_path: str
    start_index: int
    end_index: int
    entries: list[SubtitleEntry]


def file_id_from_path(relative_path: Path) -> str:
    return relative_path.as_posix().replace("/", "__")


def chunk_entries(
    *,
    file_id: str,
    relative_path: Path,
    entries: list[SubtitleEntry],
    max_chars: int,
    max_segments: int,
) -> list[SubtitleChunk]:
    chunks: list[SubtitleChunk] = []
    bucket: list[SubtitleEntry] = []
    bucket_chars = 0
    chunk_number = 1

    for entry in entries:
        entry_chars = len(entry.text) + 16
        if bucket and (len(bucket) >= max_segments or bucket_chars + entry_chars > max_chars):
            chunks.append(
                SubtitleChunk(
                    chunk_id=f"{file_id}__chunk_{chunk_number:04d}",
                    file_id=file_id,
                    relative_path=relative_path.as_posix(),
                    start_index=bucket[0].index,
                    end_index=bucket[-1].index,
                    entries=list(bucket),
                )
            )
            chunk_number += 1
            bucket = []
            bucket_chars = 0

        bucket.append(entry)
        bucket_chars += entry_chars

    if bucket:
        chunks.append(
            SubtitleChunk(
                chunk_id=f"{file_id}__chunk_{chunk_number:04d}",
                file_id=file_id,
                relative_path=relative_path.as_posix(),
                start_index=bucket[0].index,
                end_index=bucket[-1].index,
                entries=list(bucket),
            )
        )

    return chunks
