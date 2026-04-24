from __future__ import annotations

from pathlib import Path

from lr2rt.models import LightroomSettings
from lr2rt.parsers.dng import parse_dng_file
from lr2rt.parsers.xmp import parse_xmp_file


SUPPORTED_EXTENSIONS = {".xmp", ".dng"}


def parse_lightroom_file(path: Path, camera_raw_namespace: str) -> LightroomSettings:
    suffix = path.suffix.lower()
    if suffix == ".xmp":
        return parse_xmp_file(path, camera_raw_namespace)
    if suffix == ".dng":
        return parse_dng_file(path, camera_raw_namespace)
    raise ValueError(
        f"Unsupported input file type {suffix!r}. Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )
