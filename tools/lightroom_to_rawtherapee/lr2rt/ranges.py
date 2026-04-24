from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from numbers import Real
from typing import Any


@dataclass(frozen=True, slots=True)
class ValueRange:
    kind: str
    minimum: float | None = None
    maximum: float | None = None
    default: float | None = None
    step: float | None = None
    unit: str | None = None


RangeCatalog = dict[str, dict[str, ValueRange]]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Real):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_default_range_catalog() -> RangeCatalog:
    raw = resources.files("lr2rt.mappings").joinpath("rawtherapee_ranges.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    sections = payload.get("sections", {})
    if not isinstance(sections, dict):
        return {}

    catalog: RangeCatalog = {}
    for section_name, section_values in sections.items():
        if not isinstance(section_values, dict):
            continue
        parsed_section: dict[str, ValueRange] = {}
        for key, spec in section_values.items():
            if not isinstance(spec, dict):
                continue
            parsed_section[key] = ValueRange(
                kind=str(spec.get("kind", "float")),
                minimum=_as_float(spec.get("min")),
                maximum=_as_float(spec.get("max")),
                default=_as_float(spec.get("default")),
                step=_as_float(spec.get("step")),
                unit=spec.get("unit"),
            )
        catalog[section_name] = parsed_section
    return catalog


def get_value_range(catalog: RangeCatalog, section: str, key: str) -> ValueRange | None:
    section_values = catalog.get(section)
    if section_values is None:
        return None
    return section_values.get(key)


def clamp_to_value_range(value: Any, value_range: ValueRange | None) -> Any:
    if value_range is None:
        return value
    if value_range.minimum is None or value_range.maximum is None:
        return value
    if isinstance(value, bool) or not isinstance(value, Real):
        return value

    clamped = max(value_range.minimum, min(value_range.maximum, float(value)))
    if isinstance(value, int):
        return int(round(clamped))
    return clamped

