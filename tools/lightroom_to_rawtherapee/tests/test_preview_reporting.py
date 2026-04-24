from pathlib import Path
import tempfile
import unittest

from lr2rt.models import ConversionResult, MappedValue
from lr2rt.reporting.preview import render_terminal_preview, write_html_preview


class PreviewReportingTests(unittest.TestCase):
    def test_terminal_preview_formats_source_precision_like_output(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="Exposure2012",
                    source_value=0.35,
                    section="Exposure",
                    key="Compensation",
                    value="0.350",
                ),
                MappedValue(
                    source_key="Contrast2012",
                    source_value=15,
                    section="Exposure",
                    key="Contrast",
                    value="12",
                ),
            ],
        )

        preview = render_terminal_preview(result)

        self.assertIn("Exposure2012=0.350", preview)
        self.assertIn("Contrast2012=15", preview)

    def test_html_preview_formats_source_precision_like_output(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="Tint",
                    source_value=13.2,
                    section="White Balance",
                    key="Green",
                    value="0.947",
                ),
                MappedValue(
                    source_key="Whites2012",
                    source_value=14.0,
                    section="Exposure",
                    key="HighlightComprThreshold",
                    value="14",
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("<small>13.200</small>", html)
        self.assertIn("<small>14</small>", html)
        self.assertIn("class=\"range-track\"", html)
        self.assertIn("class=\"range-marker range-default\"", html)
        self.assertIn("class=\"range-marker range-value\"", html)
        self.assertIn("default", html)

    def test_html_preview_hides_enabled_rows_and_groups_sections(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="Vibrance",
                    source_value=10,
                    section="Vibrance",
                    key="Pastels",
                    value="10",
                ),
                MappedValue(
                    source_key="Contrast2012",
                    source_value=20,
                    section="Exposure",
                    key="Contrast",
                    value="16",
                ),
                MappedValue(
                    source_key="Vibrance",
                    source_value=10,
                    section="Vibrance",
                    key="Enabled",
                    value="true",
                ),
                MappedValue(
                    source_key="Vibrance",
                    source_value=10,
                    section="Vibrance",
                    key="Saturated",
                    value="10",
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertNotIn("Vibrance/Enabled", html)
        self.assertIn("Hidden enable-toggle rows: 1", html)
        self.assertIn("class=\"mapping-row group-start\"", html)
        self.assertIn("class=\"mapping-row group-end\"", html)

        # Ensure section-grouped ordering in HTML: Vibrance entries are adjacent.
        pastels_idx = html.find("Vibrance/Pastels")
        saturated_idx = html.find("Vibrance/Saturated")
        exposure_idx = html.find("Exposure/Contrast")
        self.assertTrue(pastels_idx != -1 and saturated_idx != -1 and exposure_idx != -1)
        self.assertLess(pastels_idx, saturated_idx)
        self.assertLess(saturated_idx, exposure_idx)

    def test_html_preview_hides_rows_that_match_defaults(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="PerspectiveHorizontal",
                    source_value=0,
                    section="Perspective",
                    key="Horizontal",
                    value="0",
                ),
                MappedValue(
                    source_key="Contrast2012",
                    source_value=20,
                    section="Exposure",
                    key="Contrast",
                    value="16",
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("Hidden default-value rows: 1", html)
        self.assertNotIn("Perspective/Horizontal", html)
        self.assertIn("Exposure/Contrast", html)


if __name__ == "__main__":
    unittest.main()
