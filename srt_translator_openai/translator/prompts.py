from __future__ import annotations

import hashlib
import json

from translator.chunking import SubtitleChunk


PROMPT_VERSION = "bjj-es-v5"


def _split_glossary_lines(glossary_lines: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    keep: list[str] = []
    prefer: list[str] = []
    avoid: list[str] = []
    general: list[str] = []

    for line in glossary_lines:
        if line.startswith("KEEP:"):
            keep.append(line.removeprefix("KEEP:").strip())
        elif line.startswith("PREFER:"):
            prefer.append(line.removeprefix("PREFER:").strip())
        elif line.startswith("AVOID:"):
            avoid.append(line.removeprefix("AVOID:").strip())
        else:
            general.append(line)

    return keep, prefer, avoid, general


def build_system_prompt(*, target_language: str, course_context: str, glossary_lines: list[str]) -> str:
    keep_lines, prefer_lines, avoid_lines, general_lines = _split_glossary_lines(glossary_lines)
    keep_block = "\n".join(f"- {line}" for line in keep_lines) if keep_lines else "- No explicit keep-as-is terms provided."
    prefer_block = "\n".join(f"- {line}" for line in prefer_lines) if prefer_lines else "- No explicit preferred renderings provided."
    avoid_block = "\n".join(f"- {line}" for line in avoid_lines) if avoid_lines else "- No explicit avoid rules provided."
    glossary_block = "\n".join(f"- {line}" for line in general_lines) if general_lines else "- No glossary provided."
    return (
        f"Translate BJJ instructional subtitles into {target_language}.\n"
        "Return only JSON matching the schema.\n"
        "Rules:\n"
        "- Keep subtitle count and index values exactly.\n"
        "- Use natural Latin American Spanish for grapplers.\n"
        "- Preserve technical meaning over literal wording.\n"
        "- Keep subtitles concise and readable.\n"
        "- No notes, explanations, labels, or file references.\n"
        "- Keep useful directional detail: left/right, near/far, inside/outside, top/bottom.\n"
        "- Preserve named BJJ terms when mat language sounds better than a literal translation.\n"
        "- Compress empty filler lightly, but never remove real instruction.\n"
        "- Translate each item independently; do not merge or split items.\n"
        "- Prefer glossary conventions when relevant.\n"
        f"Course context: {course_context}\n"
        "Preferred keep-as-is terms:\n"
        f"{keep_block}\n"
        "Preferred renderings:\n"
        f"{prefer_block}\n"
        "Avoid these literal or awkward renderings:\n"
        f"{avoid_block}\n"
        "Glossary:\n"
        f"{glossary_block}"
    )


def build_user_payload(chunk: SubtitleChunk) -> dict[str, object]:
    return {
        "items": [{"index": entry.index, "text": entry.text} for entry in chunk.entries],
    }


def translation_schema() -> dict[str, object]:
    return {
        "type": "json_schema",
        "name": "srt_translation_chunk",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "index": {"type": "integer"},
                            "translated_text": {"type": "string"},
                        },
                        "required": ["index", "translated_text"],
                    },
                }
            },
            "required": ["items"],
        },
    }


def request_dedup_key(
    *,
    model: str,
    system_prompt: str,
    user_payload: dict[str, object],
) -> str:
    data = json.dumps(
        {
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
