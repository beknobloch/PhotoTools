from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any

from lr2rt.config import load_config
from lr2rt.mapper import MappingEngine
from lr2rt.models import ConversionResult
from lr2rt.parsers import parse_lightroom_file
from lr2rt.pp3_writer import serialize_pp3, write_pp3
from lr2rt.pp3_template import merge_pp3_sections, parse_pp3_file
from lr2rt.quality import STRICT_FAILURE_EXIT_CODE, evaluate_strict_mode
from lr2rt.reporting import render_terminal_preview, write_html_preview


def _load_pipeline(mapping_file: str | None, profile: str) -> tuple[str, MappingEngine]:
    override_path = Path(mapping_file).expanduser().resolve() if mapping_file else None
    config = load_config(override_path)
    namespace = config.get("metadata_namespaces", {}).get("crs", "http://ns.adobe.com/camera-raw-settings/1.0/")
    engine = MappingEngine(config, profile_name=profile)
    return namespace, engine


def _run_conversion(input_file: Path, mapping_file: str | None, profile: str) -> ConversionResult:
    namespace, engine = _load_pipeline(mapping_file, profile)
    settings = parse_lightroom_file(input_file, namespace)
    return engine.convert(settings)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="Path to input Lightroom preset (.xmp or .dng)")
    parser.add_argument("--profile", default="balanced", help="Mapping profile name (default: balanced)")
    parser.add_argument(
        "--mapping-file",
        help="Optional JSON file to override or extend default mappings.",
    )
    parser.add_argument(
        "--base-pp3",
        type=Path,
        help="Optional existing .pp3 profile used as a template (keeps full RawTherapee key set).",
    )
    parser.add_argument(
        "--base-pp3-mode",
        choices=("safe", "preserve"),
        default="safe",
        help=(
            "How to merge --base-pp3. "
            "'safe' keeps compatibility structure while preventing template look leakage (default). "
            "'preserve' keeps all base values and only overrides mapped keys."
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lr2rt",
        description="Convert Lightroom preset metadata (.xmp/.dng) into RawTherapee profile files (.pp3).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    profiles_parser = subparsers.add_parser("profiles", help="List mapping profiles")
    profiles_parser.add_argument("--mapping-file", help="Optional JSON file to override or extend default mappings.")

    preview_parser = subparsers.add_parser("preview", help="Preview mapped settings before writing PP3")
    _add_common_arguments(preview_parser)
    preview_parser.add_argument("--html-report", type=Path, help="Optional output path for rich HTML preview report")
    preview_parser.add_argument("--json", action="store_true", help="Print preview as JSON payload")
    preview_parser.add_argument("--show-pp3", action="store_true", help="Print generated PP3 text to stdout")

    convert_parser = subparsers.add_parser("convert", help="Convert Lightroom preset into .pp3")
    _add_common_arguments(convert_parser)
    convert_parser.add_argument("output", nargs="?", type=Path, help="Output .pp3 path (default: input filename with .pp3)")
    convert_parser.add_argument("--dry-run", action="store_true", help="Run conversion but do not write output file")
    convert_parser.add_argument("--html-report", type=Path, help="Optional output path for HTML preview report")
    convert_parser.add_argument("--stdout", action="store_true", help="Print PP3 content to stdout")
    convert_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail conversion if any warnings are produced and skip writing output.",
    )

    gui_parser = subparsers.add_parser("gui", help="Open the desktop UI for queued conversion")
    gui_parser.add_argument(
        "--profile",
        default=None,
        help="Mapping profile name override. Defaults to last GUI selection.",
    )
    gui_parser.add_argument("--mapping-file", help="Optional JSON file to override or extend default mappings.")
    gui_parser.add_argument(
        "--base-pp3",
        type=Path,
        help="Optional existing .pp3 profile used as a template (keeps full RawTherapee key set).",
    )
    gui_parser.add_argument(
        "--base-pp3-mode",
        choices=("safe", "preserve"),
        default=None,
        help=(
            "How to merge --base-pp3. "
            "'safe' keeps compatibility structure while preventing template look leakage. "
            "'preserve' keeps all base values and only overrides mapped keys."
        ),
    )
    gui_parser.add_argument(
        "--strict",
        action="store_true",
        default=None,
        help="Open GUI with strict mode enabled by default.",
    )

    return parser


def _apply_base_profile(result: ConversionResult, base_pp3: Path | None, base_pp3_mode: str = "safe") -> ConversionResult:
    if base_pp3 is None:
        return result
    template_path = base_pp3.expanduser().resolve()
    base_sections = parse_pp3_file(template_path)

    if base_pp3_mode == "preserve":
        mapped_overrides: dict[str, dict[str, str]] = {}
        for mapped in result.mapped_values:
            mapped_overrides.setdefault(mapped.section, {})[mapped.key] = mapped.value
        result.pp3_sections = merge_pp3_sections(base_sections, mapped_overrides)
        return result

    merged = deepcopy(base_sections)

    # In safe mode, use converter-generated section bodies for known sections.
    # This avoids inheriting creative curves/operations from the template.
    converter_sections = result.pp3_sections
    for section, kv_pairs in converter_sections.items():
        merged[section] = deepcopy(kv_pairs)

    # Disable untouched template tools by default to prevent accidental look carry-over.
    converter_section_names = set(converter_sections.keys())
    for section, kv_pairs in list(merged.items()):
        if section in converter_section_names:
            continue
        if "Enabled" in kv_pairs:
            merged[section] = {"Enabled": "false"}

    result.pp3_sections = merged
    return result


def _result_to_json(result) -> str:
    payload = {
        "input_file": str(result.input_file),
        "input_format": result.input_format,
        "profile": result.profile,
        "mapped_values": [
            {
                "source_key": item.source_key,
                "source_value": item.source_value,
                "section": item.section,
                "key": item.key,
                "value": item.value,
                "used_default": item.used_default,
            }
            for item in result.mapped_values
        ],
        "warnings": [
            {"code": warning.code, "message": warning.message, "source_key": warning.source_key}
            for warning in result.warnings
        ],
        "unmapped_source_keys": result.unmapped_source_keys,
    }
    return json.dumps(payload, indent=2)


def _list_profiles(mapping_file: str | None) -> int:
    override_path = Path(mapping_file).expanduser().resolve() if mapping_file else None
    config = load_config(override_path)
    profiles = config.get("profiles", {})
    if not profiles:
        print("No mapping profiles found.")
        return 1

    print("Available mapping profiles:")
    for name, profile in profiles.items():
        description = profile.get("description", "")
        print(f"- {name}: {description}")
    return 0


def _resolve_input_file(path: Path) -> Path:
    input_file = path.expanduser().resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_file}")
    return input_file


def _write_html_report(result: ConversionResult, html_path: Path) -> Path:
    output_html = html_path.expanduser().resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)
    write_html_preview(result, output_html)
    return output_html


def _print_warnings(result: ConversionResult) -> None:
    if not result.warnings:
        return
    print("Warnings:")
    for warning in result.warnings:
        print(f"- [{warning.code}] {warning.message}")


def _handle_preview_command(args: Any, result: ConversionResult) -> int:
    if args.json:
        print(_result_to_json(result))
    else:
        print(render_terminal_preview(result))

    if args.show_pp3:
        print("\n--- Generated PP3 ---")
        print(serialize_pp3(result.pp3_sections), end="")

    if args.html_report:
        output_html = _write_html_report(result, args.html_report)
        print(f"\nHTML report written to: {output_html}")

    return 0


def _resolve_output_path(input_file: Path, output_arg: Path | None) -> Path:
    return output_arg.expanduser().resolve() if output_arg else input_file.with_suffix(".pp3")


def _handle_convert_command(args: Any, input_file: Path, result: ConversionResult) -> int:
    output_path = _resolve_output_path(input_file, args.output)
    strict_eval = evaluate_strict_mode(result, strict=bool(args.strict))

    if args.html_report:
        output_html = _write_html_report(result, args.html_report)
        print(f"HTML report written to: {output_html}")

    if args.dry_run:
        print("Dry run complete. PP3 was not written.")
        if strict_eval.failed:
            print(f"Strict mode failed: {strict_eval.message}")
        print(render_terminal_preview(result))
        return STRICT_FAILURE_EXIT_CODE if strict_eval.failed else 0

    if strict_eval.failed:
        print(f"Strict mode failed: {strict_eval.message}")
        _print_warnings(result)
        print(f"Skipped writing output file: {output_path}")
        return STRICT_FAILURE_EXIT_CODE

    if args.stdout:
        print(serialize_pp3(result.pp3_sections), end="")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_pp3(output_path, result.pp3_sections)

    print(f"Converted {input_file.name} -> {output_path}")
    print(f"Mapped values: {len(result.mapped_values)} | Warnings: {len(result.warnings)}")
    _print_warnings(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "profiles":
            return _list_profiles(args.mapping_file)
        if args.command == "gui":
            from lr2rt.gui import launch_gui

            launch_gui(
                profile=args.profile,
                mapping_file=args.mapping_file,
                base_pp3=args.base_pp3,
                base_pp3_mode=args.base_pp3_mode,
                strict=args.strict,
            )
            return 0

        input_file = _resolve_input_file(args.input)

        result = _run_conversion(input_file, args.mapping_file, args.profile)
        result = _apply_base_profile(result, args.base_pp3, args.base_pp3_mode)

        if args.command == "preview":
            return _handle_preview_command(args, result)

        return _handle_convert_command(args, input_file, result)

    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    except Exception as exc:  # pragma: no cover - CLI hardening
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
