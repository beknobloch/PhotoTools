from __future__ import annotations

from pathlib import Path

from lr2rt.models import LightroomSettings
from lr2rt.parsers.xmp import parse_xmp_text

_XMP_START_TOKENS = (b"<x:xmpmeta", b"<xmpmeta")
_XMP_END_TOKENS = (b"</x:xmpmeta>", b"</xmpmeta>")


def extract_xmp_packet_from_dng(data: bytes) -> str:
    start = -1
    for token in _XMP_START_TOKENS:
        candidate = data.find(token)
        if candidate != -1 and (start == -1 or candidate < start):
            start = candidate

    if start == -1:
        raise ValueError("No embedded XMP packet found in DNG data.")

    end = -1
    for token in _XMP_END_TOKENS:
        candidate = data.find(token, start)
        if candidate != -1:
            candidate += len(token)
            if end == -1 or candidate < end:
                end = candidate

    if end == -1:
        raise ValueError("Embedded XMP packet appears truncated in DNG data.")

    packet = data[start:end]
    try:
        return packet.decode("utf-8")
    except UnicodeDecodeError:
        return packet.decode("latin-1", errors="ignore")


def parse_dng_file(path: Path, camera_raw_namespace: str) -> LightroomSettings:
    dng_data = path.read_bytes()
    xmp_text = extract_xmp_packet_from_dng(dng_data)
    settings = parse_xmp_text(path, xmp_text, camera_raw_namespace)
    settings.source_format = "dng"
    return settings
