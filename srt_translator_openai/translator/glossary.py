from __future__ import annotations

from pathlib import Path


def load_glossary(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def select_glossary_for_text(
    glossary_lines: list[str],
    *,
    text: str,
    max_lines: int = 60,
) -> list[str]:
    haystack = f" {text.lower()} "
    matched: list[str] = []
    fallback: list[str] = []

    for line in glossary_lines:
        candidate = line
        for prefix in ("KEEP:", "PREFER:", "AVOID:"):
            if candidate.startswith(prefix):
                candidate = candidate.removeprefix(prefix).strip()
                break

        if "=>" in candidate:
            source = candidate.split("=>", 1)[0].strip().lower()
        else:
            source = candidate.strip().lower()

        source = f" {source} "
        if source.strip() and source in haystack:
            matched.append(line)
        elif len(fallback) < max_lines:
            fallback.append(line)

    if len(matched) >= max_lines:
        return matched[:max_lines]

    result = list(matched)
    for line in fallback:
        if line not in result:
            result.append(line)
        if len(result) >= max_lines:
            break
    return result
