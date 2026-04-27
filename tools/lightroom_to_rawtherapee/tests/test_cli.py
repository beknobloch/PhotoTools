from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from lr2rt.cli import _apply_base_profile, main as cli_main
from lr2rt.config import load_default_config
from lr2rt.mapper import MappingEngine
from lr2rt.parsers.xmp import parse_xmp_file
from lr2rt.quality import STRICT_FAILURE_EXIT_CODE

CAMERA_RAW_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"
FIXTURE_XMP = Path(__file__).parent / "fixtures" / "sample_preset.xmp"


def _write_warning_mapping(path: Path) -> Path:
    override = {
        "profiles": {
            "strict_test": {
                "description": "Produces a missing-source warning for strict mode tests.",
                "mappings": [
                    {
                        "source": "MissingSettingForStrictTest",
                        "target": {"section": "Exposure", "key": "Contrast"},
                        "output": {"type": "int"},
                    }
                ],
            }
        }
    }
    path.write_text(json.dumps(override), encoding="utf-8")
    return path


class CliMergeTests(unittest.TestCase):
    def test_base_profile_merge_safe_mode_prevents_template_look_leakage(self) -> None:
        settings = parse_xmp_file(FIXTURE_XMP, CAMERA_RAW_NS)
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")
        result = engine.convert(settings)

        base_pp3 = """[Exposure]\nCompensation=0\nContrast=0\nHighlightCompr=0\nHighlightComprThreshold=0\nShadowCompr=50\nCurve=4;0;0;1;1;\n\n[Luminance Curve]\nEnabled=true\nBrightness=-22\nContrast=54\nChromaticity=-41\n\n[Vibrance]\nEnabled=false\nPastels=7\nSaturated=0\n\n[ColorToning]\nEnabled=true\nMethod=RGBSliders\n"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir) / "base.pp3"
            base_path.write_text(base_pp3, encoding="utf-8")
            merged = _apply_base_profile(result, base_path)

        self.assertEqual(merged.pp3_sections["Luminance Curve"]["Brightness"], "0")
        self.assertEqual(merged.pp3_sections["Luminance Curve"]["Contrast"], "0")
        self.assertEqual(merged.pp3_sections["Vibrance"]["Pastels"], "10")
        self.assertEqual(merged.pp3_sections["Vibrance"]["Saturated"], "10")
        self.assertNotIn("Curve", merged.pp3_sections["Exposure"])
        self.assertEqual(merged.pp3_sections["ColorToning"]["Enabled"], "false")

    def test_base_profile_merge_preserve_mode_keeps_unmapped_template_values(self) -> None:
        settings = parse_xmp_file(FIXTURE_XMP, CAMERA_RAW_NS)
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")
        result = engine.convert(settings)

        base_pp3 = """[Exposure]\nCompensation=0\nContrast=0\nHighlightCompr=0\nHighlightComprThreshold=0\nShadowCompr=50\nCurve=4;0;0;1;1;\n\n[Luminance Curve]\nEnabled=true\nBrightness=-22\nContrast=54\nChromaticity=-41\n\n[Vibrance]\nEnabled=false\nPastels=7\nSaturated=0\n"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_path = Path(tmp_dir) / "base.pp3"
            base_path.write_text(base_pp3, encoding="utf-8")
            merged = _apply_base_profile(result, base_path, "preserve")

        self.assertEqual(merged.pp3_sections["Luminance Curve"]["Brightness"], "-22")
        self.assertEqual(merged.pp3_sections["Luminance Curve"]["Contrast"], "54")
        self.assertEqual(merged.pp3_sections["Vibrance"]["Pastels"], "10")
        self.assertEqual(merged.pp3_sections["Vibrance"]["Saturated"], "10")
        self.assertEqual(merged.pp3_sections["Exposure"]["Curve"], "4;0;0;1;1;")


class CliStrictModeTests(unittest.TestCase):
    def test_convert_without_strict_writes_output_even_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_path = tmp_path / "out.pp3"
            mapping_path = _write_warning_mapping(tmp_path / "override.json")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(
                    [
                        "convert",
                        str(FIXTURE_XMP),
                        str(output_path),
                        "--profile",
                        "strict_test",
                        "--mapping-file",
                        str(mapping_path),
                    ]
                )
            output_exists = output_path.exists()

        self.assertEqual(code, 0)
        self.assertTrue(output_exists)

    def test_convert_with_strict_fails_and_skips_output_when_warnings_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_path = tmp_path / "strict_fail.pp3"
            mapping_path = _write_warning_mapping(tmp_path / "override.json")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(
                    [
                        "convert",
                        str(FIXTURE_XMP),
                        str(output_path),
                        "--profile",
                        "strict_test",
                        "--mapping-file",
                        str(mapping_path),
                        "--strict",
                    ]
                )

        self.assertEqual(code, STRICT_FAILURE_EXIT_CODE)
        self.assertFalse(output_path.exists())
        text = stdout.getvalue()
        self.assertIn("Strict mode failed", text)
        self.assertIn("Warnings:", text)

    def test_convert_with_strict_passes_and_writes_output_without_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_path = tmp_path / "strict_pass.pp3"

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(["convert", str(FIXTURE_XMP), str(output_path), "--strict"])
            output_exists = output_path.exists()

        self.assertEqual(code, 0)
        self.assertTrue(output_exists)

    def test_convert_with_strict_and_dry_run_returns_strict_failure_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output_path = tmp_path / "dry_run_fail.pp3"
            mapping_path = _write_warning_mapping(tmp_path / "override.json")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(
                    [
                        "convert",
                        str(FIXTURE_XMP),
                        str(output_path),
                        "--profile",
                        "strict_test",
                        "--mapping-file",
                        str(mapping_path),
                        "--strict",
                        "--dry-run",
                    ]
                )

        self.assertEqual(code, STRICT_FAILURE_EXIT_CODE)
        self.assertFalse(output_path.exists())

    def test_convert_with_strict_does_not_emit_pp3_stdout_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mapping_path = _write_warning_mapping(tmp_path / "override.json")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli_main(
                    [
                        "convert",
                        str(FIXTURE_XMP),
                        "--profile",
                        "strict_test",
                        "--mapping-file",
                        str(mapping_path),
                        "--strict",
                        "--stdout",
                    ]
                )

        self.assertEqual(code, STRICT_FAILURE_EXIT_CODE)
        text = stdout.getvalue()
        self.assertIn("Strict mode failed", text)
        self.assertNotIn("[Version]", text)


if __name__ == "__main__":
    unittest.main()
