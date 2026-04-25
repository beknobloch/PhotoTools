from __future__ import annotations

import re
from copy import deepcopy
from numbers import Real
from typing import Any

from lr2rt.models import ConversionResult, ConversionWarning, LightroomSettings, MappedValue
from lr2rt.ranges import RangeCatalog, clamp_to_value_range, get_value_range, load_default_range_catalog

_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_SKIP_MAPPING = object()


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _to_float(value: Any) -> float:
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise TypeError("empty string is not numeric")
        return float(normalized)
    raise TypeError(f"Expected numeric value, got {type(value).__name__}")


def _parse_tone_curve_pairs(value: Any) -> list[tuple[float, float]]:
    pairs: list[tuple[float, float]] = []

    if isinstance(value, list):
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                pairs.append((_to_float(item[0]), _to_float(item[1])))
                continue
            if isinstance(item, str):
                numbers = [float(n) for n in _NUMBER_RE.findall(item)]
                if len(numbers) >= 2:
                    pairs.append((numbers[0], numbers[1]))
        return pairs

    if isinstance(value, str):
        numbers = [float(n) for n in _NUMBER_RE.findall(value)]
        for idx in range(0, len(numbers) - 1, 2):
            pairs.append((numbers[idx], numbers[idx + 1]))
        return pairs

    return pairs


def _hsv_point_values(source_values: dict[str, Any], keys: list[str]) -> list[float]:
    values = [float(source_values.get(key, 0)) for key in keys]
    if len(values) != 8:
        raise ValueError("lr_hsv_curve transform expects exactly 8 source values")

    red, orange, yellow, green, aqua, blue, purple, magenta = values
    return [
        red,
        (orange + yellow) / 2.0,
        green,
        aqua,
        (blue + purple) / 2.0,
        magenta,
    ]


def _serialize_hsv_curve(points: list[float], scale: float, base: float, tang: float) -> str:
    if len(points) != 6:
        raise ValueError("HSV curve serialization expects 6 control points")

    serialized = ["1"]
    for idx, point in enumerate(points):
        x = idx / 6.0
        y = _clamp(base + (point * scale), 0.0, 1.0)
        serialized.extend([f"{x:.6f}", f"{y:.6f}", f"{tang:.6f}", f"{tang:.6f}"])
    return ";".join(serialized) + ";"


def _is_positiveish(value: Any, threshold: float) -> bool:
    if isinstance(value, dict):
        return any(_is_positiveish(item, threshold) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_is_positiveish(item, threshold) for item in value)
    if isinstance(value, Real):
        return float(value) > threshold
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        try:
            return float(stripped) > threshold
        except ValueError:
            return True
    return bool(value)


def _is_nonzeroish(value: Any, threshold: float) -> bool:
    if isinstance(value, dict):
        return any(_is_nonzeroish(item, threshold) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_is_nonzeroish(item, threshold) for item in value)
    if isinstance(value, Real):
        return abs(float(value)) > threshold
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False
        try:
            return abs(float(stripped)) > threshold
        except ValueError:
            return True
    return bool(value)


def _apply_transform(value: Any, transform: dict[str, Any]) -> Any:
    transform_type = transform.get("type", "identity")

    if transform_type == "identity":
        return value

    if transform_type == "linear":
        numeric = _to_float(value)
        scale = float(transform.get("scale", 1.0))
        offset = float(transform.get("offset", 0.0))
        return numeric * scale + offset

    if transform_type == "weighted_sum":
        if not isinstance(value, dict):
            raise TypeError("weighted_sum transform expects object input from mapping.sources")

        weights_cfg = transform.get("weights")
        if not isinstance(weights_cfg, dict) or not weights_cfg:
            raise ValueError("weighted_sum transform requires a non-empty weights object")

        total = 0.0
        for source_key, weight in weights_cfg.items():
            total += _to_float(value[source_key]) * float(weight)
        return total

    if transform_type == "clamp":
        numeric = _to_float(value)
        minimum = float(transform.get("min", numeric))
        maximum = float(transform.get("max", numeric))
        return _clamp(numeric, minimum, maximum)

    if transform_type == "invert":
        numeric = _to_float(value)
        pivot = float(transform.get("pivot", 0.0))
        return pivot - (numeric - pivot)

    if transform_type == "round":
        numeric = _to_float(value)
        digits = int(transform.get("digits", 0))
        return round(numeric, digits)

    if transform_type == "constant":
        return transform.get("value", "")

    if transform_type == "abs":
        return abs(_to_float(value))

    if transform_type == "skip_if_default":
        numeric = _to_float(value)
        default_value = float(transform.get("value", 0.0))
        epsilon = float(transform.get("epsilon", 1e-9))
        if abs(numeric - default_value) <= epsilon:
            return _SKIP_MAPPING
        return numeric

    if transform_type == "skip_if_outside":
        numeric = _to_float(value)
        minimum = float(transform.get("min", float("-inf")))
        maximum = float(transform.get("max", float("inf")))
        if numeric < minimum or numeric > maximum:
            return _SKIP_MAPPING
        return numeric

    if transform_type == "skip_if_false":
        return value if bool(value) else _SKIP_MAPPING

    if transform_type == "any_nondefault_in_range":
        epsilon = float(transform.get("epsilon", 1e-9))
        defaults_cfg = transform.get("defaults", {})
        if defaults_cfg is None:
            defaults_cfg = {}
        if not isinstance(defaults_cfg, dict):
            raise ValueError("any_nondefault_in_range defaults must be an object")

        ranges_cfg = transform.get("ranges", {})
        if ranges_cfg is None:
            ranges_cfg = {}
        if not isinstance(ranges_cfg, dict):
            raise ValueError("any_nondefault_in_range ranges must be an object")

        if isinstance(value, dict):
            keys_cfg = transform.get("keys")
            keys = [str(k) for k in keys_cfg] if isinstance(keys_cfg, list) else list(value.keys())
            any_nondefault = False
            for key in keys:
                if key not in value:
                    continue
                numeric = _to_float(value[key])
                range_spec = ranges_cfg.get(key, {})
                if range_spec is None:
                    range_spec = {}
                if not isinstance(range_spec, dict):
                    raise ValueError("any_nondefault_in_range range specs must be objects")
                minimum = float(range_spec.get("min", float("-inf")))
                maximum = float(range_spec.get("max", float("inf")))
                if numeric < minimum or numeric > maximum:
                    return False
                default_value = float(defaults_cfg.get(key, 0.0))
                if abs(numeric - default_value) > epsilon:
                    any_nondefault = True
            return any_nondefault

        numeric = _to_float(value)
        minimum = float(transform.get("min", float("-inf")))
        maximum = float(transform.get("max", float("inf")))
        if numeric < minimum or numeric > maximum:
            return False
        default_value = float(transform.get("value", 0.0))
        return abs(numeric - default_value) > epsilon

    if transform_type == "lr_tonecurve_to_rt":
        pairs = _parse_tone_curve_pairs(value)
        if len(pairs) < 2:
            return "0;"

        normalize = bool(transform.get("normalize", True))
        x_divisor = float(transform.get("x_divisor", 255.0))
        y_divisor = float(transform.get("y_divisor", 255.0))

        converted: list[tuple[float, float]] = []
        for x, y in pairs:
            if normalize:
                x = x / x_divisor
                y = y / y_divisor
            converted.append((_clamp(x, 0.0, 1.0), _clamp(y, 0.0, 1.0)))

        # RawTherapee RGB curves serialize as "1;<x1>;<y1>;...;<xn>;<yn>;".
        # The leading "1" is a curve format marker, not a point-count.
        values = ["1"]
        for x, y in converted:
            values.extend([f"{x:.6f}", f"{y:.6f}"])
        return ";".join(values) + ";"

    if transform_type == "lr_hsv_curve":
        if not isinstance(value, dict):
            raise TypeError("lr_hsv_curve transform expects object input from mapping.sources")

        keys = transform.get("keys")
        if not isinstance(keys, list) or len(keys) != 8:
            raise ValueError("lr_hsv_curve transform requires transform.keys with 8 Lightroom HSL keys")

        scale = float(transform.get("scale", 0.0025))
        base = float(transform.get("base", 0.5))
        tang = float(transform.get("tangent", 0.35))

        points = _hsv_point_values(value, keys)
        return _serialize_hsv_curve(points, scale=scale, base=base, tang=tang)

    if transform_type == "lr_hsv_curve_with_calibration":
        if not isinstance(value, dict):
            raise TypeError("lr_hsv_curve_with_calibration expects object input from mapping.sources")

        hsl_keys = transform.get("hsl_keys")
        if not isinstance(hsl_keys, list) or len(hsl_keys) != 8:
            raise ValueError("lr_hsv_curve_with_calibration requires hsl_keys list with 8 entries")

        calibration_keys = transform.get("calibration_keys")
        if not isinstance(calibration_keys, list) or len(calibration_keys) != 3:
            raise ValueError("lr_hsv_curve_with_calibration requires calibration_keys list with 3 entries")

        scale = float(transform.get("scale", 0.0025))
        base = float(transform.get("base", 0.5))
        tang = float(transform.get("tangent", 0.35))
        calibration_scale = float(transform.get("calibration_scale", 0.35))

        points = _hsv_point_values(value, hsl_keys)
        c_red = float(value.get(calibration_keys[0], 0.0)) * calibration_scale
        c_green = float(value.get(calibration_keys[1], 0.0)) * calibration_scale
        c_blue = float(value.get(calibration_keys[2], 0.0)) * calibration_scale

        points[0] += c_red * 0.8
        points[1] += c_red * 0.3 + c_green * 0.2
        points[2] += c_green * 0.8
        points[3] += c_blue * 0.3 + c_green * 0.2
        points[4] += c_blue * 0.8
        points[5] += c_red * 0.2 + c_blue * 0.3

        return _serialize_hsv_curve(points, scale=scale, base=base, tang=tang)

    if transform_type == "lr_sat_hue_pair":
        if isinstance(value, dict):
            sat_key = str(transform.get("sat_key", "sat"))
            hue_key = str(transform.get("hue_key", "hue"))
            sat_value = _to_float(value[sat_key])
            hue_value = _to_float(value[hue_key])
        elif isinstance(value, (list, tuple)) and len(value) >= 2:
            sat_value = _to_float(value[0])
            hue_value = _to_float(value[1])
        else:
            raise TypeError("lr_sat_hue_pair transform expects object or two-item list input")

        sat_min = float(transform.get("sat_min", 0.0))
        sat_max = float(transform.get("sat_max", 100.0))
        hue_min = float(transform.get("hue_min", 0.0))
        hue_max = float(transform.get("hue_max", 360.0))
        if bool(transform.get("reject_outside", False)):
            if sat_value < sat_min or sat_value > sat_max or hue_value < hue_min or hue_value > hue_max:
                return _SKIP_MAPPING

        sat_scale = float(transform.get("sat_scale", 1.0))
        sat_value *= sat_scale
        sat_value = _clamp(sat_value, sat_min, sat_max)
        hue_value = _clamp(hue_value, hue_min, hue_max)

        if bool(transform.get("skip_if_default_sat", False)):
            default_sat = float(transform.get("default_sat", 0.0))
            epsilon = float(transform.get("epsilon", 1e-9))
            if abs(sat_value - default_sat) <= epsilon:
                return _SKIP_MAPPING

        return f"{int(round(sat_value))};{int(round(hue_value))};"

    if transform_type == "any_positive":
        threshold = float(transform.get("threshold", 0.0))
        return _is_positiveish(value, threshold)

    if transform_type == "any_nonzero":
        threshold = float(transform.get("threshold", 0.0))
        return _is_nonzeroish(value, threshold)

    if transform_type == "lr_parametric_split_to_regularization":
        if not isinstance(value, dict):
            raise TypeError("lr_parametric_split_to_regularization expects object input from mapping.sources")

        shadow_key = str(transform.get("shadow_key", "ParametricShadowSplit"))
        highlight_key = str(transform.get("highlight_key", "ParametricHighlightSplit"))
        default_width = float(transform.get("default_width", 50.0))
        scale = float(transform.get("scale", 0.1))

        shadow_split = _to_float(value[shadow_key])
        highlight_split = _to_float(value[highlight_key])
        width = highlight_split - shadow_split
        return (width - default_width) * scale

    raise ValueError(f"Unknown transform type {transform_type!r}")


def _format_output(value: Any, output_cfg: dict[str, Any] | None) -> str:
    if output_cfg is None:
        return str(value)

    output_type = output_cfg.get("type", "raw")
    if output_type == "raw":
        return str(value)
    if output_type == "int":
        return str(int(round(_to_float(value))))
    if output_type == "float":
        precision = int(output_cfg.get("precision", 3))
        formatted = f"{_to_float(value):.{precision}f}"
        if bool(output_cfg.get("trim_trailing_zeros", False)):
            formatted = formatted.rstrip("0").rstrip(".")
            if formatted in {"-0", "-0.0", ""}:
                formatted = "0"
        return formatted
    if output_type == "bool":
        return "true" if bool(value) else "false"
    raise ValueError(f"Unknown output type {output_type!r}")


class MappingEngine:
    def __init__(self, config: dict[str, Any], profile_name: str = "balanced") -> None:
        profiles = config.get("profiles", {})
        if profile_name not in profiles:
            available = ", ".join(sorted(profiles.keys()))
            raise ValueError(f"Unknown profile {profile_name!r}. Available profiles: {available}")

        self.profile_name = profile_name
        self.profile = profiles[profile_name]
        self.static_sections = deepcopy(config.get("static_sections", {}))
        self.range_catalog: RangeCatalog = load_default_range_catalog()

    def _resolve_source_value(
        self, mapping: dict[str, Any], settings: LightroomSettings, result: ConversionResult, consumed_source_keys: set[str]
    ) -> tuple[str, Any, bool] | None:
        if "sources" in mapping:
            source_keys = mapping["sources"]
            if not isinstance(source_keys, list) or not source_keys:
                raise ValueError("mapping.sources must be a non-empty list")

            defaults_map = mapping.get("defaults", {})
            if defaults_map is None:
                defaults_map = {}
            if not isinstance(defaults_map, dict):
                raise ValueError("mapping.defaults must be an object when provided")

            resolved: dict[str, Any] = {}
            used_default = False
            missing: list[str] = []

            for key in source_keys:
                if key in settings.values:
                    resolved[key] = settings.values[key]
                    consumed_source_keys.add(key)
                elif key in defaults_map:
                    resolved[key] = defaults_map[key]
                    used_default = True
                else:
                    missing.append(key)

            if missing:
                if mapping.get("optional", False):
                    return None
                result.warnings.append(
                    ConversionWarning(
                        code="MISSING_SOURCE",
                        source_key=",".join(source_keys),
                        message=f"Missing required source metadata keys: {', '.join(missing)}. Mapping skipped.",
                    )
                )
                return None

            source_key = "+".join(source_keys)
            if used_default and not bool(mapping.get("suppress_default_warning", False)):
                result.warnings.append(
                    ConversionWarning(
                        code="DEFAULT_APPLIED",
                        source_key=source_key,
                        message=f"Some source metadata keys were missing. Defaults applied for mapping {source_key}.",
                    )
                )

            return source_key, resolved, used_default

        source_key = mapping["source"]
        used_default = False

        if source_key in settings.values:
            source_value = settings.values[source_key]
            consumed_source_keys.add(source_key)
        elif "default" in mapping:
            source_value = mapping["default"]
            used_default = True
            result.warnings.append(
                ConversionWarning(
                    code="DEFAULT_APPLIED",
                    source_key=source_key,
                    message=f"{source_key} missing in input metadata. Using default value {source_value}.",
                )
            )
        else:
            if mapping.get("optional", False):
                return None
            result.warnings.append(
                ConversionWarning(
                    code="MISSING_SOURCE",
                    source_key=source_key,
                    message=f"{source_key} missing in input metadata. Mapping skipped.",
                )
            )
            return None

        return source_key, source_value, used_default

    def convert(self, settings: LightroomSettings) -> ConversionResult:
        result = ConversionResult(
            input_file=settings.source_path,
            input_format=settings.source_format,
            profile=self.profile_name,
            pp3_sections=deepcopy(self.static_sections),
        )

        consumed_source_keys: set[str] = set()
        mappings = self.profile.get("mappings", [])

        for mapping in mappings:
            target = mapping["target"]
            section = target["section"]
            key = target["key"]
            resolved = self._resolve_source_value(mapping, settings, result, consumed_source_keys)
            if resolved is None:
                continue
            source_key, source_value, used_default = resolved

            try:
                transformed_value = source_value
                skip_mapping = False
                for transform in mapping.get("transforms", []):
                    transformed_value = _apply_transform(transformed_value, transform)
                    if transformed_value is _SKIP_MAPPING:
                        skip_mapping = True
                        break
                if skip_mapping:
                    continue
                if not mapping.get("skip_target_range_clamp", False):
                    value_range = get_value_range(self.range_catalog, section, key)
                    transformed_value = clamp_to_value_range(transformed_value, value_range)
                output_value = _format_output(transformed_value, mapping.get("output"))
            except (TypeError, ValueError, KeyError) as exc:
                result.warnings.append(
                    ConversionWarning(
                        code="TRANSFORM_ERROR",
                        source_key=source_key,
                        message=f"Failed mapping for {source_key}: {exc}",
                    )
                )
                continue

            result.pp3_sections.setdefault(section, {})[key] = output_value
            result.mapped_values.append(
                MappedValue(
                    source_key=source_key,
                    source_value=source_value,
                    section=section,
                    key=key,
                    value=output_value,
                    used_default=used_default,
                )
            )

        result.unmapped_source_keys = sorted(set(settings.values.keys()) - consumed_source_keys)
        return result
