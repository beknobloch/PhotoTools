from pathlib import Path
import tempfile
import unittest

from lr2rt.cli import _apply_base_profile
from lr2rt.config import load_default_config
from lr2rt.mapper import MappingEngine
from lr2rt.parsers.xmp import parse_xmp_file

CAMERA_RAW_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"
FIXTURE_XMP = Path(__file__).parent / "fixtures" / "sample_preset.xmp"


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


if __name__ == "__main__":
    unittest.main()
