from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from lr2rt.models import LightroomSettings

_NUMBER_PATTERN = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def _coerce_scalar(value: str) -> Any:
    normalized = value.strip()
    if _NUMBER_PATTERN.fullmatch(normalized):
        if "." in normalized:
            return float(normalized)
        return int(normalized)
    return normalized


def _extract_local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _extract_rdf_list(element: ET.Element) -> list[Any]:
    items: list[Any] = []
    for li in element.findall(f".//{{{_RDF_NS}}}li"):
        if li.text and li.text.strip():
            items.append(_coerce_scalar(li.text))
    return items


def parse_xmp_text(path: Path, xmp_text: str, camera_raw_namespace: str) -> LightroomSettings:
    try:
        root = ET.fromstring(xmp_text)
    except ET.ParseError as exc:
        raise ValueError(f"Unable to parse XMP metadata in {path}: {exc}") from exc

    values: dict[str, Any] = {}

    for element in root.iter():
        for attr_name, attr_value in element.attrib.items():
            if attr_name.startswith("{" + camera_raw_namespace + "}"):
                key = attr_name.split("}", 1)[1]
                values[key] = _coerce_scalar(attr_value)

        namespace_match = element.tag.startswith("{" + camera_raw_namespace + "}")
        if namespace_match:
            key = _extract_local_name(element.tag)
            list_items = _extract_rdf_list(element)
            if list_items:
                values[key] = list_items
                continue
            if element.text and element.text.strip():
                values[key] = _coerce_scalar(element.text)

    return LightroomSettings(source_path=path, source_format="xmp", values=values, raw_xmp=xmp_text)


def parse_xmp_file(path: Path, camera_raw_namespace: str) -> LightroomSettings:
    xmp_text = path.read_text(encoding="utf-8", errors="ignore")
    settings = parse_xmp_text(path, xmp_text, camera_raw_namespace)
    settings.source_format = "xmp"
    return settings
