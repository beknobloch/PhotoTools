from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Iterable

from lr2rt.models import MappedValue


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


def apply_base_profile_mode(
    base_sections: dict[str, dict[str, str]],
    converter_sections: dict[str, dict[str, str]],
    mapped_values: Iterable[MappedValue],
    base_pp3_mode: str = "safe",
) -> dict[str, dict[str, str]]:
    if base_pp3_mode == "preserve":
        mapped_overrides: dict[str, dict[str, str]] = {}
        for mapped in mapped_values:
            mapped_overrides.setdefault(mapped.section, {})[mapped.key] = mapped.value
        return merge_pp3_sections(base_sections, mapped_overrides)

    merged = deepcopy(base_sections)

    # In safe mode, use converter-generated section bodies for known sections.
    for section, kv_pairs in converter_sections.items():
        merged[section] = deepcopy(kv_pairs)

    # Disable untouched template tools by default to prevent accidental look carry-over.
    converter_section_names = set(converter_sections.keys())
    for section, kv_pairs in list(merged.items()):
        if section in converter_section_names:
            continue
        if "Enabled" in kv_pairs:
            merged[section] = {"Enabled": "false"}

    return merged
