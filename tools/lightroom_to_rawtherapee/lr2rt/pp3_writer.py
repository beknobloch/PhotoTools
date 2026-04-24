from __future__ import annotations

from pathlib import Path


def serialize_pp3(sections: dict[str, dict[str, str]]) -> str:
    lines: list[str] = []

    for section, kv_pairs in sections.items():
        lines.append(f"[{section}]")
        for key, value in kv_pairs.items():
            safe_value = str(value).replace("\n", " ")
            lines.append(f"{key}={safe_value}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_pp3(path: Path, sections: dict[str, dict[str, str]]) -> None:
    path.write_text(serialize_pp3(sections), encoding="utf-8")
