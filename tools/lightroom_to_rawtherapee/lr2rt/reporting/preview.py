from __future__ import annotations

from html import escape
import re
from numbers import Real
from pathlib import Path
from urllib.parse import quote_plus

from lr2rt.config import load_default_config
from lr2rt.models import ConversionResult, MappedValue
from lr2rt.ranges import ValueRange, get_value_range, load_default_range_catalog

_INT_OUTPUT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_OUTPUT_RE = re.compile(r"^[+-]?\d+\.(\d+)$")
_NUMBER_TOKEN_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_RANGE_CATALOG = load_default_range_catalog()
_STATIC_DEFAULTS = {
    (section, key): str(value).strip()
    for section, kv_pairs in load_default_config().get("static_sections", {}).items()
    for key, value in kv_pairs.items()
}
_NON_MAPPABLE_LIGHTROOM_KEYS = {
    "CameraModelRestriction",
    "CameraProfileDigest",
    "Cluster",
    "ContactInfo",
    "Copyright",
    "CropConstrainToWarp",
    "Description",
    "Group",
    "HasSettings",
    "LensProfileSetup",
    "Name",
    "PresetType",
    "ProcessVersion",
    "RequiresRGBTables",
    "ShortName",
    "SortName",
    "SupportsAmount",
    "SupportsAmount2",
    "SupportsColor",
    "SupportsHighDynamicRange",
    "SupportsMonochrome",
    "SupportsNormalDynamicRange",
    "SupportsOutputReferred",
    "SupportsSceneReferred",
    "ToneCurveName2012",
    "UUID",
    "Version",
}
_RAWPEDIA_BASE_URL = "https://rawpedia.rawtherapee.com/"
_CRITICAL_WARNING_CODES = {"MISSING_SOURCE", "TRANSFORM_ERROR"}
_RAWPEDIA_TOOL_PATHS = {
    "Exposure": "Exposure",
    "White Balance": "White_Balance",
    "Shadows & Highlights": "Shadows/Highlights",
    "Luminance Curve": "Lab_Adjustments#L_Curve",
    "Vibrance": "Vibrance",
    "Local Contrast": "Local_Contrast",
    "Sharpening": "Sharpening",
    "SharpenMicro": "Edges_and_Microcontrast#Microcontrast",
    "PostDemosaicSharpening": "Resize#Post-Resize_Sharpening",
    "Dehaze": "Haze_Removal",
    "Directional Pyramid Denoising": "Noise_Reduction",
    "RGB Curves": "RGB_Curves",
    "HSV Equalizer": "HSV_Equalizer",
    "ColorToning": "Color_Toning",
    "PCVignette": "Vignetting_Filter",
    "Vignetting Correction": "Lens/Geometry#Vignetting_Correction",
    "Perspective": "Lens/Geometry#Perspective",
    "Rotation": "Lens/Geometry#Rotate",
    "Distortion": "Lens/Geometry#Geometric_Distortion",
    "LensProfile": "Lens/Geometry#Profiled_Lens_Correction",
    "Defringing": "Defringe",
    "Directional Pyramid Equalizer": "Contrast_by_Detail_Levels",
    "ToneEqualizer": "Local_Adjustments#Tone_equalizer",
}


def _pad(value: str, width: int) -> str:
    return value.ljust(width)


def _format_source_value(mapped: MappedValue) -> str:
    source_value = mapped.source_value
    if isinstance(source_value, bool) or not isinstance(source_value, Real):
        return str(source_value)

    output_value = mapped.value.strip()
    float_match = _FLOAT_OUTPUT_RE.fullmatch(output_value)
    if float_match:
        precision = len(float_match.group(1))
        return f"{float(source_value):.{precision}f}"

    if _INT_OUTPUT_RE.fullmatch(output_value) and float(source_value).is_integer():
        return str(int(source_value))

    return str(source_value)


def _format_mapping_row(mapped: MappedValue) -> tuple[str, str, str, str]:
    source_display = f"{mapped.source_key}={_format_source_value(mapped)}"
    target_display = f"{mapped.section}/{mapped.key}"
    output_display = mapped.value
    default_marker = "default" if mapped.used_default else "source"
    return source_display, target_display, output_display, default_marker


def _truncate_middle(value: str, max_len: int = 78, tail: int = 24) -> str:
    if len(value) <= max_len:
        return value
    head = max_len - tail - 3
    if head < 8:
        return value[: max_len - 3] + "..."
    return f"{value[:head]}...{value[-tail:]}"


def _highlight_numeric_fragments(value: str) -> str:
    rendered: list[str] = []
    last_idx = 0
    for match in _NUMBER_TOKEN_RE.finditer(value):
        start, end = match.span()
        if start > last_idx:
            rendered.append(escape(value[last_idx:start]))
        rendered.append(f"<span class=\"source-num\">{escape(match.group(0))}</span>")
        last_idx = end
    if last_idx < len(value):
        rendered.append(escape(value[last_idx:]))
    return "".join(rendered) if rendered else escape(value)


def _section_color(section: str) -> str:
    # Deterministic per-section color for visual grouping.
    hue = sum(ord(ch) for ch in section) % 360
    return f"hsl({hue} 50% 42%)"


def _rawpedia_doc_url(section: str, key: str) -> str:
    if section in _RAWPEDIA_TOOL_PATHS:
        return _RAWPEDIA_BASE_URL + _RAWPEDIA_TOOL_PATHS[section]
    query = quote_plus(f"{section} {key} RawTherapee")
    return f"{_RAWPEDIA_BASE_URL}index.php?search={query}"


def _severity_for_mapping(mapped: MappedValue, warning_codes_by_source: dict[str, set[str]]) -> str:
    warning_codes = warning_codes_by_source.get(mapped.source_key, set())
    if any(code in _CRITICAL_WARNING_CODES for code in warning_codes):
        return "critical"
    if warning_codes or mapped.used_default:
        return "warning"
    return "ok"


def _severity_badge_class(severity: str) -> str:
    if severity == "critical":
        return "critical"
    if severity == "warning":
        return "warn"
    return "ok"


def _mapping_row_html(
    mapped: MappedValue,
    group_class: str,
    group_color: str,
    severity: str,
    is_default_output: bool,
) -> str:
    source_origin = "default" if mapped.used_default else "source"
    chip_class = "warn" if mapped.used_default else "ok"
    severity_badge = _severity_badge_class(severity)
    source_value = _format_source_value(mapped)
    range_html = _range_visual_html(mapped)
    output_html = _render_output_html(mapped.value)
    source_key_full = mapped.source_key
    source_key_display = _truncate_middle(source_key_full)
    source_value_html = _highlight_numeric_fragments(source_value)
    doc_url = _rawpedia_doc_url(mapped.section, mapped.key)
    row_classes = f"mapping-row {group_class} row-link"
    row_attrs = (
        f" data-doc-url=\"{escape(doc_url)}\" tabindex=\"0\" role=\"link\""
        f" data-is-default=\"{'true' if is_default_output else 'false'}\""
        f" data-severity=\"{escape(severity)}\""
        f" data-has-warning=\"{'true' if severity != 'ok' else 'false'}\""
        f" aria-label=\"Open RawPedia docs for {escape(mapped.section)} / {escape(mapped.key)}\""
    )
    return (
        f"<tr class=\"{row_classes}\" style=\"--group-color: {group_color};\"{row_attrs}>"
        f"<td class=\"col-source\"><code class=\"source-key\" title=\"{escape(source_key_full)}\">{escape(source_key_display)}</code><small class=\"source-value\">{source_value_html}</small></td>"
        f"<td class=\"col-target\"><div class=\"target-entry\"><span class=\"target-tool\">{escape(mapped.section)}</span><strong class=\"target-key\">{escape(mapped.key)}</strong></div></td>"
        f"<td class=\"col-output\">{output_html}{range_html}</td>"
        f"<td class=\"col-origin\"><span class=\"chip {chip_class}\">{source_origin}</span><span class=\"chip severity {severity_badge}\">{escape(severity)}</span></td>"
        "</tr>"
    )


def _parse_numeric_text(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    if _INT_OUTPUT_RE.fullmatch(stripped) or _FLOAT_OUTPUT_RE.fullmatch(stripped):
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _is_default_mapped_value(mapped: MappedValue) -> bool:
    output_text = mapped.value.strip()
    if not output_text:
        return False

    value_range = get_value_range(_RANGE_CATALOG, mapped.section, mapped.key)
    output_numeric = _parse_numeric_text(output_text)
    if value_range is not None and value_range.default is not None and output_numeric is not None:
        tolerance = 1e-6
        if abs(output_numeric - value_range.default) <= tolerance:
            return True

    static_default = _STATIC_DEFAULTS.get((mapped.section, mapped.key))
    if static_default is None:
        return False

    if output_text == static_default:
        return True

    static_numeric = _parse_numeric_text(static_default)
    if output_numeric is not None and static_numeric is not None:
        return abs(output_numeric - static_numeric) <= 1e-6

    return output_text.lower() == static_default.lower()


def _format_range_number(value: float | None, value_range: ValueRange) -> str:
    if value is None:
        return "n/a"
    if value_range.kind == "int":
        return str(int(round(value)))
    return f"{value:.3f}"


def _value_position_percent(value: float, minimum: float, maximum: float) -> float:
    span = maximum - minimum
    if span <= 0:
        return 0.0
    return ((value - minimum) / span) * 100.0


def _range_visual_html(mapped: MappedValue) -> str:
    value_range = get_value_range(_RANGE_CATALOG, mapped.section, mapped.key)
    if value_range is None or value_range.minimum is None or value_range.maximum is None:
        return ""

    output_numeric = _parse_numeric_text(mapped.value)
    if output_numeric is None:
        return ""

    minimum = value_range.minimum
    maximum = value_range.maximum
    output_numeric = max(minimum, min(maximum, output_numeric))
    min_display = _format_range_number(minimum, value_range)
    max_display = _format_range_number(maximum, value_range)
    default_display = _format_range_number(value_range.default, value_range)
    unit_display = f" {escape(value_range.unit)}" if value_range.unit else ""
    value_left = _value_position_percent(output_numeric, minimum, maximum)
    default_marker_html = ""

    if value_range.default is not None:
        default_numeric = max(minimum, min(maximum, value_range.default))
        default_left = _value_position_percent(default_numeric, minimum, maximum)
        default_marker_html = (
            f"<span class=\"range-marker range-default\" style=\"left: {default_left:.4f}%;\"></span>"
        )

    return (
        "<div class=\"range-meta\">"
        "<div class=\"range-track\">"
        f"{default_marker_html}"
        f"<span class=\"range-marker range-value\" style=\"left: {value_left:.4f}%;\"></span>"
        "</div>"
        f"<small>min {min_display}{unit_display} · default {default_display}{unit_display} · max {max_display}{unit_display}</small>"
        "</div>"
    )


def _parse_curve_points(value: str) -> list[tuple[float, float]] | None:
    parts = [part.strip() for part in value.split(";") if part.strip()]
    if len(parts) < 5:
        return None

    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None

    rest = numbers[1:]

    # HSV-style curves are serialized as x;y;t;t quads. Detect this pattern
    # first by checking that each tangent pair is effectively equal.
    is_quad_tangent_format = (
        len(rest) >= 8
        and len(rest) % 4 == 0
        and all(abs(rest[idx + 2] - rest[idx + 3]) <= 1e-6 for idx in range(0, len(rest), 4))
    )

    if is_quad_tangent_format:
        points = [(rest[idx], rest[idx + 1]) for idx in range(0, len(rest), 4)]
    elif len(rest) >= 4 and len(rest) % 2 == 0:
        points = [(rest[idx], rest[idx + 1]) for idx in range(0, len(rest), 2)]
    else:
        return None

    if len(points) < 2:
        return None
    return points


def _curve_polyline_svg(points: list[tuple[float, float]]) -> str:
    width = 174.0
    height = 48.0
    pad = 2.0
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    if abs(max_x - min_x) < 1e-9:
        min_x -= 0.5
        max_x += 0.5
    if abs(max_y - min_y) < 1e-9:
        min_y -= 0.5
        max_y += 0.5

    span_x = max_x - min_x
    span_y = max_y - min_y

    coords: list[str] = []
    for x, y in points:
        px = pad + ((x - min_x) / span_x) * (width - (2 * pad))
        py = (height - pad) - ((y - min_y) / span_y) * (height - (2 * pad))
        coords.append(f"{px:.2f},{py:.2f}")

    polyline_points = " ".join(coords)
    return (
        f"<svg class=\"curve-mini\" viewBox=\"0 0 {int(width)} {int(height)}\" aria-hidden=\"true\" focusable=\"false\">"
        "<line x1=\"0\" y1=\"47\" x2=\"174\" y2=\"47\" class=\"curve-axis\" />"
        "<line x1=\"1\" y1=\"0\" x2=\"1\" y2=\"48\" class=\"curve-axis\" />"
        f"<polyline points=\"{polyline_points}\" class=\"curve-line\" />"
        "</svg>"
    )


def _render_output_html(value: str) -> str:
    points = _parse_curve_points(value)
    if points is None:
        return f"<strong>{escape(value)}</strong>"

    summary = f"Curve ({len(points)} pts)"
    curve_svg = _curve_polyline_svg(points)
    raw_value = escape(value)
    return (
        "<div class=\"curve-output\">"
        f"<strong>{escape(summary)}</strong>"
        f"{curve_svg}"
        "<details class=\"curve-raw\"><summary>Raw values</summary>"
        f"<code>{raw_value}</code>"
        "</details>"
        "</div>"
    )


def _group_display_mappings(mapped_values: list[MappedValue]) -> list[MappedValue]:
    grouped: dict[str, list[MappedValue]] = {}
    section_order: list[str] = []

    for mapped in mapped_values:
        if mapped.section not in grouped:
            grouped[mapped.section] = []
            section_order.append(mapped.section)
        grouped[mapped.section].append(mapped)

    ordered: list[MappedValue] = []
    for section in section_order:
        ordered.extend(grouped[section])
    return ordered


def _filter_potentially_mappable_unmapped_keys(keys: list[str]) -> list[str]:
    filtered: list[str] = []
    for key in keys:
        if key in _NON_MAPPABLE_LIGHTROOM_KEYS:
            continue
        if key.startswith("Supports"):
            continue
        filtered.append(key)
    return filtered


def render_terminal_preview(result: ConversionResult, max_rows: int = 50) -> str:
    headers = ("Source", "Target", "Output", "Origin")
    rows = [_format_mapping_row(entry) for entry in result.mapped_values[:max_rows]]

    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    separator = "-+-".join("-" * width for width in widths)
    table_lines = [
        " | ".join(_pad(header, widths[idx]) for idx, header in enumerate(headers)),
        separator,
    ]
    table_lines.extend(" | ".join(_pad(cell, widths[idx]) for idx, cell in enumerate(row)) for row in rows)

    if len(result.mapped_values) > max_rows:
        table_lines.append(f"... {len(result.mapped_values) - max_rows} more mapped values omitted.")

    summary = [
        f"Input: {result.input_file}",
        f"Profile: {result.profile}",
        f"Mapped values: {len(result.mapped_values)}",
        f"Warnings: {len(result.warnings)}",
        f"Unmapped source keys: {len(result.unmapped_source_keys)}",
        "",
        *table_lines,
    ]

    if result.warnings:
        summary.append("")
        summary.append("Warnings:")
        summary.extend(f"- [{w.code}] {w.message}" for w in result.warnings)

    if result.unmapped_source_keys:
        summary.append("")
        summary.append("Unmapped Lightroom metadata keys:")
        summary.extend(f"- {key}" for key in result.unmapped_source_keys)

    return "\n".join(summary)


def write_html_preview(result: ConversionResult, output_path: Path) -> None:
    display_mappings = [mapped for mapped in result.mapped_values if mapped.key != "Enabled"]
    hidden_enabled_rows = len(result.mapped_values) - len(display_mappings)
    default_row_count = sum(1 for mapped in display_mappings if _is_default_mapped_value(mapped))
    grouped_mappings = _group_display_mappings(display_mappings)
    mapping_rows_parts: list[str] = []

    warning_codes_by_source: dict[str, set[str]] = {}
    for warning in result.warnings:
        if warning.source_key:
            warning_codes_by_source.setdefault(warning.source_key, set()).add(warning.code)

    severity_counts = {"critical": 0, "warning": 0, "ok": 0}

    for idx, mapped in enumerate(grouped_mappings):
        prev_section = grouped_mappings[idx - 1].section if idx > 0 else None
        next_section = grouped_mappings[idx + 1].section if idx + 1 < len(grouped_mappings) else None

        if prev_section != mapped.section and next_section != mapped.section:
            group_class = "group-single"
        elif prev_section != mapped.section:
            group_class = "group-start"
        elif next_section != mapped.section:
            group_class = "group-end"
        else:
            group_class = "group-mid"

        severity = _severity_for_mapping(mapped, warning_codes_by_source)
        is_default_output = _is_default_mapped_value(mapped)
        severity_counts[severity] += 1
        mapping_rows_parts.append(
            _mapping_row_html(
                mapped=mapped,
                group_class=group_class,
                group_color=_section_color(mapped.section),
                severity=severity,
                is_default_output=is_default_output,
            )
        )

    mapping_rows = "\n".join(mapping_rows_parts)
    hidden_enabled_note = (
        f"<p class=\"note\">Hidden enable-toggle rows: {hidden_enabled_rows}</p>" if hidden_enabled_rows else ""
    )
    default_rows_note = f"<p class=\"note\">Default-value rows available for filtering: {default_row_count}</p>"

    display_unmapped_keys = _filter_potentially_mappable_unmapped_keys(result.unmapped_source_keys)

    warning_items = "\n".join(
        f"<li><strong>{escape(warning.code)}</strong>: {escape(warning.message)}</li>" for warning in result.warnings
    ) or "<li>None</li>"

    unmapped_items = "\n".join(f"<li><code>{escape(key)}</code></li>" for key in display_unmapped_keys) or "<li>None</li>"

    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>lr2rt Preview</title>
    <style>
      :root {{
        --bg-0: #090a0c;
        --bg-1: #111318;
        --panel: #171a20;
        --panel-soft: #1c2027;
        --text: #ece6d9;
        --muted: #b2ab9e;
        --accent: #d3b173;
        --accent-2: #8f7043;
        --ok: #90ba9d;
        --warn: #d8a06b;
        --border: #3b3225;
        --table-line: #2d3138;
        --font-body: "Adobe Caslon Pro", "Iowan Old Style", "Baskerville", "Palatino Linotype", serif;
        --font-display: "Bodoni 72", "Didot", "Times New Roman", serif;
        --font-tech: "Courier Prime", "Courier New", "Nimbus Mono PS", monospace;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        font-family: var(--font-body);
        background:
          radial-gradient(1200px circle at 8% -10%, rgba(211, 177, 115, 0.15) 0%, rgba(211, 177, 115, 0) 50%),
          radial-gradient(900px circle at 105% 0%, rgba(143, 112, 67, 0.16) 0%, rgba(143, 112, 67, 0) 45%),
          linear-gradient(180deg, var(--bg-1), var(--bg-0));
        color: var(--text);
      }}
      .wrap {{
        max-width: 1100px;
        margin: 0 auto;
        padding: 28px 24px 34px;
      }}
      .title {{
        font-family: var(--font-display);
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-weight: 600;
        font-size: 2rem;
        margin: 0 0 8px;
        color: #f5efe2;
      }}
      p {{
        color: var(--muted);
      }}
      p strong {{
        color: var(--text);
      }}
      h2 {{
        margin-top: 0;
        margin-bottom: 10px;
        font-family: var(--font-display);
        letter-spacing: 0.045em;
        text-transform: uppercase;
        color: #f0e7d4;
      }}
      .summary {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 14px;
        margin: 20px 0 24px;
      }}
      .card {{
        background: linear-gradient(180deg, var(--panel-soft), var(--panel));
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 13px;
        box-shadow:
          inset 0 1px 0 rgba(255, 255, 255, 0.03),
          0 14px 30px rgba(0, 0, 0, 0.34);
      }}
      .label {{
        color: var(--muted);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}
      .value {{
        font-family: var(--font-tech);
        font-size: 1.2rem;
        color: #f8f1df;
      }}
      .note {{
        margin: -10px 0 14px;
        color: var(--muted);
        font-size: 0.84rem;
      }}
      .filters {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin: 0 0 12px;
      }}
      .toggle {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        font-size: 0.84rem;
        color: #ede4d2;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 7px 11px;
      }}
      .toggle input {{
        accent-color: var(--accent);
      }}
      .severity-strip {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 0 0 12px;
      }}
      table {{
        width: 100%;
        table-layout: fixed;
        border-collapse: collapse;
        background: linear-gradient(180deg, #13161b, #101318);
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
        box-shadow:
          inset 0 1px 0 rgba(255, 255, 255, 0.03),
          0 18px 34px rgba(0, 0, 0, 0.4);
      }}
      th, td {{
        text-align: left;
        padding: 10px 11px;
        border-bottom: 1px solid var(--table-line);
        vertical-align: top;
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      td code, td small, td strong {{
        display: block;
        white-space: normal;
        overflow-wrap: anywhere;
        word-break: break-word;
      }}
      td small {{
        margin-top: 4px;
        color: var(--muted);
      }}
      td strong {{
        color: #fbf3df;
      }}
      code {{
        font-family: var(--font-tech);
        color: #f6edd9;
      }}
      .source-key {{
        color: #f8eed9;
      }}
      .source-value {{
        margin-top: 6px;
        display: block;
        padding: 3px 6px;
        border-radius: 5px;
        background: rgba(255, 255, 255, 0.03);
        color: #d9cfbb;
        font-family: var(--font-tech);
        font-size: 0.78rem;
        line-height: 1.3;
      }}
      .source-num {{
        color: #f4e4c1;
        font-weight: 650;
      }}
      .target-entry {{
        display: grid;
        gap: 3px;
      }}
      .target-tool {{
        color: #c0b8a7;
        font-size: 0.78rem;
        letter-spacing: 0.04em;
        font-weight: 350;
        text-transform: uppercase;
      }}
      .target-key {{
        color: #f9f2e2;
        font-size: 0.95rem;
        font-weight: 700;
      }}
      col.col-source {{ width: 26%; }}
      col.col-target {{ width: 28%; }}
      col.col-output {{ width: 36%; }}
      col.col-origin {{ width: 10%; }}
      @media (max-width: 980px) {{
        col.col-source {{ width: 25%; }}
        col.col-target {{ width: 27%; }}
        col.col-output {{ width: 34%; }}
        col.col-origin {{ width: 12%; }}
      }}
      th {{
        background: linear-gradient(90deg, rgba(211, 177, 115, 0.26), rgba(143, 112, 67, 0.14));
        color: #f7efdc;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.78rem;
        border-bottom: 1px solid rgba(211, 177, 115, 0.42);
      }}
      .mapping-row td:first-child {{
        border-left: 4px solid var(--group-color);
      }}
      .mapping-row.group-start td {{
        padding-top: 16px;
      }}
      .mapping-row.group-end td {{
        padding-bottom: 16px;
      }}
      .mapping-row.group-single td {{
        padding-top: 14px;
        padding-bottom: 14px;
      }}
      .mapping-row.row-link {{
        cursor: pointer;
      }}
      .mapping-row.row-link td {{
        transition: background-color 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
      }}
      .mapping-row.row-link:hover td {{
        background: rgba(211, 177, 115, 0.075);
      }}
      .mapping-row.row-link:hover td:first-child {{
        box-shadow: inset 2px 0 0 rgba(243, 224, 181, 0.75);
      }}
      .mapping-row.row-link:focus-visible {{
        outline: 2px solid rgba(211, 177, 115, 0.72);
        outline-offset: -2px;
      }}
      .mapping-row.is-hidden {{
        display: none;
      }}
      .chip {{
        display: inline-block;
        border-radius: 999px;
        padding: 4px 8px;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        border: 1px solid transparent;
      }}
      .chip.ok {{
        background: rgba(144, 186, 157, 0.12);
        color: var(--ok);
        border-color: rgba(144, 186, 157, 0.35);
      }}
      .chip.warn {{
        background: rgba(216, 160, 107, 0.12);
        color: var(--warn);
        border-color: rgba(216, 160, 107, 0.35);
      }}
      .chip.severity {{
        margin-top: 6px;
      }}
      .chip.critical {{
        background: rgba(210, 92, 92, 0.12);
        color: #f0a6a6;
        border-color: rgba(210, 92, 92, 0.4);
      }}
      .range-meta {{
        margin-top: 6px;
      }}
      .curve-output {{
        display: block;
      }}
      .curve-mini {{
        display: block;
        width: min(100%, 220px);
        height: 52px;
        margin-top: 6px;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.015);
      }}
      .curve-axis {{
        stroke: rgba(236, 230, 217, 0.15);
        stroke-width: 1;
      }}
      .curve-line {{
        fill: none;
        stroke: var(--accent);
        stroke-width: 1.8;
        stroke-linecap: round;
        stroke-linejoin: round;
      }}
      .curve-raw {{
        margin-top: 6px;
      }}
      .curve-raw summary {{
        cursor: pointer;
        color: var(--muted);
        font-size: 0.72rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      .curve-raw code {{
        margin-top: 6px;
        display: block;
        font-size: 0.76rem;
        color: #d8cdb8;
      }}
      .range-track {{
        position: relative;
        height: 8px;
        width: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, rgba(211, 177, 115, 0.24), rgba(143, 112, 67, 0.22));
      }}
      .range-marker {{
        position: absolute;
        top: 50%;
        transform: translate(-50%, -50%);
        border-radius: 999px;
      }}
      .range-marker.range-value {{
        width: 12px;
        height: 12px;
        background: var(--accent);
        border: 2px solid #19140e;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.22);
      }}
      .range-marker.range-default {{
        width: 8px;
        height: 8px;
        background: transparent;
        border: 2px solid #ddd1b7;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.45);
      }}
      .range-meta small {{
        display: block;
        color: var(--muted);
        margin-top: 4px;
        font-size: 0.74rem;
      }}
      .range-meta .range-track + small {{
        margin: 0;
      }}
      .panes {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 12px;
        margin-top: 18px;
      }}
      ul {{
        margin: 0;
        padding-left: 18px;
      }}
      li {{
        color: var(--text);
        margin-bottom: 3px;
      }}
    </style>
  </head>
  <body>
    <div class=\"wrap\">
      <h1 class=\"title\">lr2rt Conversion Preview</h1>
      <p><strong>Input:</strong> {escape(str(result.input_file))}<br /><strong>Profile:</strong> {escape(result.profile)}</p>

      <section class=\"summary\">
        <div class=\"card\"><div class=\"label\">Mapped</div><div class=\"value\">{len(grouped_mappings)}</div></div>
        <div class=\"card\"><div class=\"label\">Warnings</div><div class=\"value\">{len(result.warnings)}</div></div>
        <div class=\"card\"><div class=\"label\">Unmapped Keys</div><div class=\"value\">{len(display_unmapped_keys)}</div></div>
      </section>
      <div class=\"severity-strip\">
        <span class=\"chip severity critical\">critical {severity_counts['critical']}</span>
        <span class=\"chip severity warn\">warning {severity_counts['warning']}</span>
        <span class=\"chip severity ok\">ok {severity_counts['ok']}</span>
      </div>
      <section class=\"filters\">
        <label class=\"toggle\"><input id=\"toggle-nondefault\" type=\"checkbox\" checked /> Show only non-default outputs</label>
        <label class=\"toggle\"><input id=\"toggle-warnings\" type=\"checkbox\" /> Show only warnings</label>
      </section>
      {hidden_enabled_note}
      {default_rows_note}
      <p id=\"visible-row-note\" class=\"note\"></p>

      <table>
        <colgroup>
          <col class="col-source" />
          <col class="col-target" />
          <col class="col-output" />
          <col class="col-origin" />
        </colgroup>
        <thead>
          <tr><th>Source</th><th>RawTherapee Target</th><th>Output</th><th>Origin</th></tr>
        </thead>
        <tbody>
          {mapping_rows}
        </tbody>
      </table>

      <section class=\"panes\">
        <div class=\"card\">
          <h2>Warnings</h2>
          <ul>{warning_items}</ul>
        </div>
        <div class=\"card\">
          <h2>Unmapped Lightroom Keys</h2>
          <ul>{unmapped_items}</ul>
        </div>
      </section>
    </div>
    <script>
      (() => {{
        const rows = document.querySelectorAll("tr.row-link[data-doc-url]");
        const toggleNonDefault = document.getElementById("toggle-nondefault");
        const toggleWarnings = document.getElementById("toggle-warnings");
        const visibleRowNote = document.getElementById("visible-row-note");

        const applyFilters = () => {{
          let visible = 0;
          rows.forEach((row) => {{
            const isDefault = row.getAttribute("data-is-default") === "true";
            const hasWarning = row.getAttribute("data-has-warning") === "true";
            let show = true;
            if (toggleNonDefault && toggleNonDefault.checked && isDefault) {{
              show = false;
            }}
            if (toggleWarnings && toggleWarnings.checked && !hasWarning) {{
              show = false;
            }}
            row.classList.toggle("is-hidden", !show);
            if (show) {{
              visible += 1;
            }}
          }});
          if (visibleRowNote) {{
            visibleRowNote.textContent = `Visible rows: ${{visible}} / ${{rows.length}}`;
          }}
        }};

        const shouldIgnoreClick = (event) => Boolean(event.target.closest("details, summary, a, button, input, textarea, select"));
        const openDocs = (row) => {{
          const url = row.getAttribute("data-doc-url");
          if (!url) return;
          window.open(url, "_blank", "noopener,noreferrer");
        }};

        rows.forEach((row) => {{
          row.addEventListener("click", (event) => {{
            if (shouldIgnoreClick(event)) return;
            openDocs(row);
          }});
          row.addEventListener("keydown", (event) => {{
            if (event.key !== "Enter" && event.key !== " ") return;
            if (shouldIgnoreClick(event)) return;
            event.preventDefault();
            openDocs(row);
          }});
        }});

        if (toggleNonDefault) {{
          toggleNonDefault.addEventListener("change", applyFilters);
        }}
        if (toggleWarnings) {{
          toggleWarnings.addEventListener("change", applyFilters);
        }}
        applyFilters();
      }})();
    </script>
  </body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
