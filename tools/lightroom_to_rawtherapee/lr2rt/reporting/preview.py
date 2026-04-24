from __future__ import annotations

from html import escape
import re
from numbers import Real
from pathlib import Path

from lr2rt.config import load_default_config
from lr2rt.models import ConversionResult, MappedValue
from lr2rt.ranges import ValueRange, get_value_range, load_default_range_catalog

_INT_OUTPUT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_OUTPUT_RE = re.compile(r"^[+-]?\d+\.(\d+)$")
_RANGE_CATALOG = load_default_range_catalog()
_STATIC_DEFAULTS = {
    (section, key): str(value).strip()
    for section, kv_pairs in load_default_config().get("static_sections", {}).items()
    for key, value in kv_pairs.items()
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


def _section_color(section: str) -> str:
    # Deterministic per-section color for visual grouping.
    hue = sum(ord(ch) for ch in section) % 360
    return f"hsl({hue} 50% 42%)"


def _mapping_row_html(mapped: MappedValue, group_class: str, group_color: str) -> str:
    source_origin = "default" if mapped.used_default else "source"
    chip_class = "warn" if mapped.used_default else "ok"
    source_value = _format_source_value(mapped)
    range_html = _range_visual_html(mapped)
    return (
        f"<tr class=\"mapping-row {group_class}\" style=\"--group-color: {group_color};\">"
        f"<td class=\"col-source\"><code>{escape(mapped.source_key)}</code><small>{escape(source_value)}</small></td>"
        f"<td class=\"col-target\"><code>{escape(mapped.section)}/{escape(mapped.key)}</code></td>"
        f"<td class=\"col-output\"><strong>{escape(mapped.value)}</strong>{range_html}</td>"
        f"<td class=\"col-origin\"><span class=\"chip {chip_class}\">{source_origin}</span></td>"
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
    visible_mappings = [mapped for mapped in result.mapped_values if mapped.key != "Enabled"]
    hidden_enabled_rows = len(result.mapped_values) - len(visible_mappings)
    before_default_filter = len(visible_mappings)
    visible_mappings = [mapped for mapped in visible_mappings if not _is_default_mapped_value(mapped)]
    hidden_default_rows = before_default_filter - len(visible_mappings)
    grouped_mappings = _group_display_mappings(visible_mappings)
    mapping_rows_parts: list[str] = []

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

        mapping_rows_parts.append(
            _mapping_row_html(
                mapped=mapped,
                group_class=group_class,
                group_color=_section_color(mapped.section),
            )
        )

    mapping_rows = "\n".join(mapping_rows_parts)
    hidden_enabled_note = (
        f"<p class=\"note\">Hidden enable-toggle rows: {hidden_enabled_rows}</p>" if hidden_enabled_rows else ""
    )
    hidden_defaults_note = (
        f"<p class=\"note\">Hidden default-value rows: {hidden_default_rows}</p>" if hidden_default_rows else ""
    )

    warning_items = "\n".join(
        f"<li><strong>{escape(warning.code)}</strong>: {escape(warning.message)}</li>" for warning in result.warnings
    ) or "<li>None</li>"

    unmapped_items = "\n".join(f"<li><code>{escape(key)}</code></li>" for key in result.unmapped_source_keys) or "<li>None</li>"

    html = f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>lr2rt Preview</title>
    <style>
      :root {{
        --bg: #f6f4ed;
        --panel: #fffdf7;
        --text: #1e2126;
        --accent: #005f73;
        --accent-2: #ee9b00;
        --muted: #5b636a;
        --ok: #2a9d8f;
        --warn: #bc6c25;
        --border: #d9d2c3;
      }}
      body {{
        margin: 0;
        font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
        background: radial-gradient(circle at top right, #ffe8d6 0%, var(--bg) 35%, #e9f4f2 100%);
        color: var(--text);
      }}
      .wrap {{
        max-width: 1100px;
        margin: 0 auto;
        padding: 24px;
      }}
      .title {{
        font-family: "Space Grotesk", "Avenir Next", sans-serif;
        letter-spacing: 0.02em;
        margin-bottom: 8px;
      }}
      .summary {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        margin: 18px 0 24px;
      }}
      .card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.04);
      }}
      .label {{
        color: var(--muted);
        font-size: 0.85rem;
      }}
      .value {{
        font-family: "Space Mono", monospace;
        font-size: 1.2rem;
      }}
      .note {{
        margin: -10px 0 14px;
        color: var(--muted);
        font-size: 0.84rem;
      }}
      table {{
        width: 100%;
        table-layout: fixed;
        border-collapse: collapse;
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
      }}
      th, td {{
        text-align: left;
        padding: 10px;
        border-bottom: 1px solid #efe8d9;
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
      }}
      col.col-source {{ width: 34%; }}
      col.col-target {{ width: 30%; }}
      col.col-output {{ width: 26%; }}
      col.col-origin {{ width: 10%; }}
      @media (max-width: 980px) {{
        col.col-source {{ width: 32%; }}
        col.col-target {{ width: 30%; }}
        col.col-output {{ width: 26%; }}
        col.col-origin {{ width: 12%; }}
      }}
      th {{
        background: linear-gradient(90deg, rgba(0,95,115,0.08), rgba(238,155,0,0.08));
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
      .chip {{
        display: inline-block;
        border-radius: 999px;
        padding: 3px 8px;
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }}
      .chip.ok {{ background: rgba(42,157,143,0.14); color: var(--ok); }}
      .chip.warn {{ background: rgba(188,108,37,0.14); color: var(--warn); }}
      .range-meta {{
        margin-top: 6px;
      }}
      .range-track {{
        position: relative;
        height: 8px;
        width: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, rgba(0,95,115,0.18), rgba(238,155,0,0.18));
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
        border: 2px solid #fff;
        box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.14);
      }}
      .range-marker.range-default {{
        width: 8px;
        height: 8px;
        background: transparent;
        border: 2px solid var(--muted);
        box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.7);
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
    </style>
  </head>
  <body>
    <div class=\"wrap\">
      <h1 class=\"title\">lr2rt Conversion Preview</h1>
      <p><strong>Input:</strong> {escape(str(result.input_file))}<br /><strong>Profile:</strong> {escape(result.profile)}</p>

      <section class=\"summary\">
        <div class=\"card\"><div class=\"label\">Mapped</div><div class=\"value\">{len(grouped_mappings)}</div></div>
        <div class=\"card\"><div class=\"label\">Warnings</div><div class=\"value\">{len(result.warnings)}</div></div>
        <div class=\"card\"><div class=\"label\">Unmapped Keys</div><div class=\"value\">{len(result.unmapped_source_keys)}</div></div>
      </section>
      {hidden_enabled_note}
      {hidden_defaults_note}

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
  </body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
