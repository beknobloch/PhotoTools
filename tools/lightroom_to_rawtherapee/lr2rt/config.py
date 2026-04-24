from __future__ import annotations

import json
from copy import deepcopy
from importlib import resources
from pathlib import Path
from typing import Any


ConfigDict = dict[str, Any]


class ConfigError(RuntimeError):
    """Raised when mapping configuration is invalid."""


def _deep_merge(base: ConfigDict, override: ConfigDict) -> ConfigDict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        merged[key] = deepcopy(value)
    return merged


def load_default_config() -> ConfigDict:
    raw = resources.files("lr2rt.mappings").joinpath("default_mapping.json").read_text(encoding="utf-8")
    config = json.loads(raw)
    validate_config(config)
    return config


def load_config(override_path: Path | None = None) -> ConfigDict:
    config = load_default_config()
    if override_path is None:
        return config
    override = json.loads(override_path.read_text(encoding="utf-8"))
    merged = _deep_merge(config, override)
    validate_config(merged)
    return merged


def validate_config(config: ConfigDict) -> None:
    if "profiles" not in config or not isinstance(config["profiles"], dict):
        raise ConfigError("Invalid mapping config: missing profiles object.")
    for profile_name, profile in config["profiles"].items():
        if not isinstance(profile, dict):
            raise ConfigError(f"Invalid profile {profile_name!r}: expected object.")
        mappings = profile.get("mappings")
        if not isinstance(mappings, list):
            raise ConfigError(f"Invalid profile {profile_name!r}: mappings must be a list.")
        for idx, mapping in enumerate(mappings):
            if not isinstance(mapping, dict):
                raise ConfigError(f"Invalid mapping #{idx} in profile {profile_name!r}: expected object.")
            has_source = "source" in mapping
            has_sources = "sources" in mapping
            if not has_source and not has_sources:
                raise ConfigError(
                    f"Invalid mapping #{idx} in profile {profile_name!r}: missing source/sources."
                )
            if has_source and has_sources:
                raise ConfigError(
                    f"Invalid mapping #{idx} in profile {profile_name!r}: use either source or sources, not both."
                )
            if has_sources and (not isinstance(mapping["sources"], list) or not mapping["sources"]):
                raise ConfigError(
                    f"Invalid mapping #{idx} in profile {profile_name!r}: sources must be a non-empty list."
                )
            target = mapping.get("target")
            if not isinstance(target, dict) or "section" not in target or "key" not in target:
                raise ConfigError(
                    f"Invalid mapping #{idx} in profile {profile_name!r}: target.section and target.key are required."
                )
