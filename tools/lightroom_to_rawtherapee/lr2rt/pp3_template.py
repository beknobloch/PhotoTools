from __future__ import annotations

from copy import deepcopy
from pathlib import Path


def parse_pp3_file(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current_section: str | None = None

    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            sections.setdefault(current_section, {})
            continue

        if current_section is None or "=" not in line:
            continue

        key, value = line.split("=", 1)
        sections[current_section][key.strip()] = value.strip()

    return sections


def merge_pp3_sections(base: dict[str, dict[str, str]], overrides: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    merged = deepcopy(base)
    for section, kv_pairs in overrides.items():
        merged.setdefault(section, {})
        merged[section].update(kv_pairs)
    return merged
