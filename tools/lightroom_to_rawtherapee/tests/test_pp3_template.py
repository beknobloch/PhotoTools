from pathlib import Path
import tempfile
import unittest

from lr2rt.pp3_template import merge_pp3_sections, parse_pp3_file


class Pp3TemplateTests(unittest.TestCase):
    def test_parse_pp3_file_extracts_sections(self) -> None:
        content = """[Exposure]\nCompensation=0.2\nContrast=10\n\n[White Balance]\nTemperature=5500\n"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "template.pp3"
            path.write_text(content, encoding="utf-8")
            parsed = parse_pp3_file(path)

        self.assertEqual(parsed["Exposure"]["Compensation"], "0.2")
        self.assertEqual(parsed["White Balance"]["Temperature"], "5500")

    def test_merge_pp3_sections_overrides_target_keys_only(self) -> None:
        base = {
            "Exposure": {"Compensation": "0", "Contrast": "0", "Black": "0"},
            "White Balance": {"Temperature": "5000", "Green": "1"},
        }
        overrides = {
            "Exposure": {"Compensation": "0.350", "Contrast": "12"},
            "Vibrance": {"Enabled": "true", "Saturated": "20"},
        }

        merged = merge_pp3_sections(base, overrides)

        self.assertEqual(merged["Exposure"]["Compensation"], "0.350")
        self.assertEqual(merged["Exposure"]["Black"], "0")
        self.assertEqual(merged["White Balance"]["Temperature"], "5000")
        self.assertIn("Vibrance", merged)


if __name__ == "__main__":
    unittest.main()
