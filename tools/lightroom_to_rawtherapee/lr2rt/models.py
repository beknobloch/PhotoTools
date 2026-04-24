from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LightroomSettings:
    source_path: Path
    source_format: str
    values: dict[str, Any]
    raw_xmp: str | None = None


@dataclass(slots=True)
class ConversionWarning:
    code: str
    message: str
    source_key: str | None = None


@dataclass(slots=True)
class MappedValue:
    source_key: str
    source_value: Any
    section: str
    key: str
    value: str
    used_default: bool = False


@dataclass(slots=True)
class ConversionResult:
    input_file: Path
    input_format: str
    profile: str
    mapped_values: list[MappedValue] = field(default_factory=list)
    unmapped_source_keys: list[str] = field(default_factory=list)
    warnings: list[ConversionWarning] = field(default_factory=list)
    pp3_sections: dict[str, dict[str, str]] = field(default_factory=dict)
