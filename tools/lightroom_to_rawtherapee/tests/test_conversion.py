from pathlib import Path
import unittest

from lr2rt.config import load_default_config
from lr2rt.mapper import MappingEngine
from lr2rt.models import LightroomSettings
from lr2rt.parsers.xmp import parse_xmp_file
from lr2rt.pp3_writer import serialize_pp3

CAMERA_RAW_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"
FIXTURE_XMP = Path(__file__).parent / "fixtures" / "sample_preset.xmp"


class ConversionTests(unittest.TestCase):
    def test_balanced_profile_maps_values(self) -> None:
        settings = parse_xmp_file(FIXTURE_XMP, CAMERA_RAW_NS)
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")

        result = engine.convert(settings)

        self.assertGreaterEqual(len(result.mapped_values), 20)
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.unmapped_source_keys, [])
        self.assertEqual(result.pp3_sections["Exposure"]["Compensation"], "0.200")
        self.assertEqual(result.pp3_sections["Exposure"]["HighlightCompr"], "0")
        self.assertEqual(result.pp3_sections["Exposure"]["ShadowCompr"], "50")
        self.assertEqual(result.pp3_sections["Shadows & Highlights"]["Highlights"], "8")
        self.assertEqual(result.pp3_sections["Shadows & Highlights"]["Shadows"], "10")
        self.assertEqual(result.pp3_sections["White Balance"]["Temperature"], "5600")
        self.assertEqual(result.pp3_sections["White Balance"]["Setting"], "Custom")
        self.assertEqual(result.pp3_sections["Luminance Curve"]["Contrast"], "0")
        self.assertEqual(result.pp3_sections["Local Contrast"]["Amount"], "0.200")
        self.assertEqual(result.pp3_sections["SharpenMicro"]["Strength"], "20")
        self.assertEqual(result.pp3_sections["PostDemosaicSharpening"]["Contrast"], "20")
        self.assertEqual(result.pp3_sections["Directional Pyramid Equalizer"]["Enabled"], "true")
        self.assertEqual(result.pp3_sections["Directional Pyramid Equalizer"]["Mult1"], "1.080")
        self.assertEqual(result.pp3_sections["Directional Pyramid Equalizer"]["Mult3"], "1.060")
        self.assertEqual(result.pp3_sections["Directional Pyramid Equalizer"]["Mult5"], "1.036")
        self.assertEqual(result.pp3_sections["Sharpening"]["Amount"], "50")
        self.assertEqual(result.pp3_sections["Dehaze"]["Strength"], "6")
        self.assertEqual(result.pp3_sections["Directional Pyramid Denoising"]["Luma"], "10")
        self.assertEqual(result.pp3_sections["Vibrance"]["Pastels"], "10")
        self.assertEqual(result.pp3_sections["Vibrance"]["Saturated"], "10")

    def test_pp3_serialization_contains_sections(self) -> None:
        settings = parse_xmp_file(FIXTURE_XMP, CAMERA_RAW_NS)
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")
        result = engine.convert(settings)

        text = serialize_pp3(result.pp3_sections)

        self.assertIn("[Exposure]", text)
        self.assertIn("Compensation=0.200", text)
        self.assertIn("[Dehaze]", text)
        self.assertIn("Strength=6", text)
        self.assertIn("[White Balance]", text)

    def test_balanced_profile_maps_curves_hsl_and_split_toning(self) -> None:
        settings = LightroomSettings(
            source_path=Path("/tmp/synthetic.xmp"),
            source_format="xmp",
            values={
                "ToneCurvePV2012Red": ["0, 0", "128, 140", "255, 255"],
                "ToneCurvePV2012Green": ["0, 0", "120, 130", "255, 255"],
                "ToneCurvePV2012Blue": ["0, 0", "110, 120", "255, 255"],
                "ToneCurvePV2012": ["0, 0", "64, 52", "180, 210", "255, 255"],
                "HueAdjustmentRed": -10,
                "HueAdjustmentOrange": -5,
                "HueAdjustmentYellow": 10,
                "HueAdjustmentGreen": 0,
                "HueAdjustmentAqua": 5,
                "HueAdjustmentBlue": 10,
                "HueAdjustmentPurple": 5,
                "HueAdjustmentMagenta": 0,
                "SaturationAdjustmentRed": 10,
                "SaturationAdjustmentOrange": 15,
                "SaturationAdjustmentYellow": 20,
                "SaturationAdjustmentGreen": -10,
                "SaturationAdjustmentAqua": 5,
                "SaturationAdjustmentBlue": 25,
                "SaturationAdjustmentPurple": 0,
                "SaturationAdjustmentMagenta": -5,
                "LuminanceAdjustmentRed": -5,
                "LuminanceAdjustmentOrange": -10,
                "LuminanceAdjustmentYellow": 5,
                "LuminanceAdjustmentGreen": -5,
                "LuminanceAdjustmentAqua": 0,
                "LuminanceAdjustmentBlue": 10,
                "LuminanceAdjustmentPurple": -10,
                "LuminanceAdjustmentMagenta": 5,
                "SplitToningHighlightHue": 40,
                "SplitToningHighlightSaturation": 12,
                "SplitToningShadowHue": 210,
                "SplitToningShadowSaturation": 22,
                "SplitToningBalance": 35,
            },
        )
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")

        result = engine.convert(settings)

        self.assertEqual(result.pp3_sections["RGB Curves"]["Enabled"], "true")
        self.assertNotEqual(result.pp3_sections["RGB Curves"]["rCurve"], "0;")
        self.assertTrue(result.pp3_sections["RGB Curves"]["rCurve"].startswith("1;"))
        self.assertTrue(result.pp3_sections["RGB Curves"]["gCurve"].startswith("1;"))
        self.assertTrue(result.pp3_sections["RGB Curves"]["bCurve"].startswith("1;"))
        self.assertTrue(result.pp3_sections["Luminance Curve"]["LCurve"].startswith("1;"))
        self.assertEqual(result.pp3_sections["HSV Equalizer"]["Enabled"], "true")
        self.assertNotEqual(result.pp3_sections["HSV Equalizer"]["SCurve"], "0;")
        self.assertEqual(result.pp3_sections["ColorToning"]["Enabled"], "true")
        self.assertEqual(result.pp3_sections["ColorToning"]["Balance"], "35")
        self.assertEqual(result.pp3_sections["ColorToning"]["HighlightsColorSaturation"], "12;40;")
        self.assertEqual(result.pp3_sections["ColorToning"]["ShadowsColorSaturation"], "22;210;")

    def test_missing_white_balance_keys_do_not_inject_temperature_or_green(self) -> None:
        settings = LightroomSettings(
            source_path=Path("/tmp/no_wb.xmp"),
            source_format="xmp",
            values={
                "Contrast2012": 10,
                "Highlights2012": -20,
            },
        )
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")

        result = engine.convert(settings)
        wb = result.pp3_sections["White Balance"]

        self.assertNotIn("Temperature", wb)
        self.assertNotIn("Green", wb)
        self.assertEqual(wb["Setting"], "Camera")

    def test_target_range_clamp_applies_without_explicit_transform_clamp(self) -> None:
        settings = LightroomSettings(
            source_path=Path("/tmp/range_clamp.xmp"),
            source_format="xmp",
            values={"Contrast2012": 999},
        )
        config = {
            "profiles": {
                "balanced": {
                    "mappings": [
                        {
                            "source": "Contrast2012",
                            "target": {"section": "Exposure", "key": "Contrast"},
                            "output": {"type": "int"},
                        }
                    ]
                }
            }
        }
        engine = MappingEngine(config, profile_name="balanced")

        result = engine.convert(settings)

        self.assertEqual(result.pp3_sections["Exposure"]["Contrast"], "100")

    def test_shadows_and_highlights_mapping_is_compression_only(self) -> None:
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")

        negative_highlights = LightroomSettings(
            source_path=Path("/tmp/highlights_negative.xmp"),
            source_format="xmp",
            values={"Highlights2012": -40, "Shadows2012": 30},
        )
        positive_highlights = LightroomSettings(
            source_path=Path("/tmp/highlights_positive.xmp"),
            source_format="xmp",
            values={"Highlights2012": 40, "Shadows2012": -30},
        )

        result_neg = engine.convert(negative_highlights)
        result_pos = engine.convert(positive_highlights)

        self.assertEqual(result_neg.pp3_sections["Shadows & Highlights"]["Highlights"], "32")
        self.assertEqual(result_neg.pp3_sections["Shadows & Highlights"]["Shadows"], "24")
        self.assertEqual(result_pos.pp3_sections["Shadows & Highlights"]["Highlights"], "0")
        self.assertEqual(result_pos.pp3_sections["Shadows & Highlights"]["Shadows"], "0")
        self.assertEqual(result_neg.pp3_sections["Exposure"]["HighlightCompr"], "0")
        self.assertEqual(result_neg.pp3_sections["Exposure"]["ShadowCompr"], "50")
        self.assertEqual(result_pos.pp3_sections["Exposure"]["HighlightCompr"], "0")
        self.assertEqual(result_pos.pp3_sections["Exposure"]["ShadowCompr"], "50")

    def test_parametric_tone_keys_map_to_tone_equalizer_in_balanced_profile(self) -> None:
        config = load_default_config()
        engine = MappingEngine(config, profile_name="balanced")
        settings = LightroomSettings(
            source_path=Path("/tmp/parametric_tone.xmp"),
            source_format="xmp",
            values={
                "ParametricShadows": -20,
                "ParametricDarks": 30,
                "ParametricLights": -50,
                "ParametricHighlights": 10,
                "ParametricShadowSplit": 20,
                "ParametricMidtoneSplit": 60,
                "ParametricHighlightSplit": 80,
            },
        )

        result = engine.convert(settings)
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Enabled"], "true")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Band0"], "-20")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Band1"], "30")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Band2"], "-50")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Band3"], "10")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Band4"], "0")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Band5"], "0")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Regularization"], "1")
        self.assertEqual(result.pp3_sections["ToneEqualizer"]["Pivot"], "2.4")
        self.assertNotIn("ParametricShadows", result.unmapped_source_keys)
        self.assertNotIn("ParametricDarks", result.unmapped_source_keys)
        self.assertNotIn("ParametricLights", result.unmapped_source_keys)
        self.assertNotIn("ParametricHighlights", result.unmapped_source_keys)
        self.assertNotIn("ParametricShadowSplit", result.unmapped_source_keys)
        self.assertNotIn("ParametricMidtoneSplit", result.unmapped_source_keys)
        self.assertNotIn("ParametricHighlightSplit", result.unmapped_source_keys)

    def test_conservative_and_aggressive_profiles_are_tuned_around_balanced(self) -> None:
        settings = parse_xmp_file(FIXTURE_XMP, CAMERA_RAW_NS)
        config = load_default_config()
        conservative = MappingEngine(config, profile_name="conservative").convert(settings).pp3_sections
        balanced = MappingEngine(config, profile_name="balanced").convert(settings).pp3_sections
        aggressive = MappingEngine(config, profile_name="aggressive").convert(settings).pp3_sections

        def as_int(sections: dict[str, dict[str, str]], section: str, key: str) -> int:
            return int(sections[section][key])

        def as_float(sections: dict[str, dict[str, str]], section: str, key: str) -> float:
            return float(sections[section][key])

        # Keep a predictable progression without making profiles wildly different.
        self.assertLessEqual(as_int(conservative, "Exposure", "Contrast"), as_int(balanced, "Exposure", "Contrast"))
        self.assertLessEqual(as_int(balanced, "Exposure", "Contrast"), as_int(aggressive, "Exposure", "Contrast"))
        self.assertLessEqual(
            as_float(conservative, "Directional Pyramid Equalizer", "Mult1"),
            as_float(balanced, "Directional Pyramid Equalizer", "Mult1"),
        )
        self.assertLessEqual(
            as_float(balanced, "Directional Pyramid Equalizer", "Mult1"),
            as_float(aggressive, "Directional Pyramid Equalizer", "Mult1"),
        )
        self.assertLessEqual(
            as_float(conservative, "Directional Pyramid Equalizer", "Mult3"),
            as_float(balanced, "Directional Pyramid Equalizer", "Mult3"),
        )
        self.assertLessEqual(
            as_float(balanced, "Directional Pyramid Equalizer", "Mult3"),
            as_float(aggressive, "Directional Pyramid Equalizer", "Mult3"),
        )
        self.assertLessEqual(as_int(conservative, "Vibrance", "Pastels"), as_int(balanced, "Vibrance", "Pastels"))
        self.assertLessEqual(as_int(balanced, "Vibrance", "Pastels"), as_int(aggressive, "Vibrance", "Pastels"))
        self.assertLessEqual(as_int(conservative, "Sharpening", "Amount"), as_int(balanced, "Sharpening", "Amount"))
        self.assertLessEqual(as_int(balanced, "Sharpening", "Amount"), as_int(aggressive, "Sharpening", "Amount"))

        self.assertLessEqual(abs(as_int(aggressive, "Exposure", "Contrast") - as_int(conservative, "Exposure", "Contrast")), 8)
        self.assertLessEqual(
            abs(
                as_float(aggressive, "Directional Pyramid Equalizer", "Mult1")
                - as_float(conservative, "Directional Pyramid Equalizer", "Mult1")
            ),
            0.6,
        )
        self.assertLessEqual(abs(as_int(aggressive, "Vibrance", "Pastels") - as_int(conservative, "Vibrance", "Pastels")), 12)

if __name__ == "__main__":
    unittest.main()
