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

        self.assertIn("class=\"source-value\"", html)
        self.assertIn(">13.200<", html)
        self.assertIn(">14<", html)
        self.assertIn("class=\"source-num\"", html)
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

        self.assertNotIn("class=\"target-key\">Enabled</strong>", html)
        self.assertIn("Hidden enable-toggle rows: 1", html)
        self.assertIn("class=\"mapping-row row-link\"", html)

        # Ensure section-grouped ordering in HTML: Vibrance entries are adjacent.
        pastels_idx = html.find("class=\"target-tool\">Vibrance</span><strong class=\"target-key\">Pastels</strong>")
        saturated_idx = html.find("class=\"target-tool\">Vibrance</span><strong class=\"target-key\">Saturated</strong>")
        exposure_idx = html.find("class=\"target-tool\">Exposure</span><strong class=\"target-key\">Contrast</strong>")
        self.assertTrue(pastels_idx != -1 and saturated_idx != -1 and exposure_idx != -1)
        self.assertLess(pastels_idx, saturated_idx)
        self.assertLess(saturated_idx, exposure_idx)

    def test_html_preview_marks_default_rows_for_toggle_filtering(self) -> None:
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

        self.assertIn("Default-value rows available for filtering: 1", html)
        self.assertIn("id=\"toggle-nondefault\"", html)
        self.assertIn("data-is-default=\"true\"", html)
        self.assertIn("class=\"target-tool\">Perspective</span><strong class=\"target-key\">Horizontal</strong>", html)
        self.assertIn("class=\"target-tool\">Exposure</span><strong class=\"target-key\">Contrast</strong>", html)

    def test_html_preview_includes_warning_toggle_and_grouped_severity_badges(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="Temperature",
                    source_value=5600,
                    section="White Balance",
                    key="Temperature",
                    value="5600",
                ),
                MappedValue(
                    source_key="Contrast2012",
                    source_value=0,
                    section="Exposure",
                    key="Contrast",
                    value="0",
                    used_default=True,
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("id=\"toggle-warnings\"", html)
        self.assertIn("class=\"severity-strip\"", html)
        self.assertIn(">critical ", html)
        self.assertIn(">warning ", html)
        self.assertIn(">ok ", html)
        self.assertIn("data-severity=\"warning\"", html)
        self.assertIn("data-has-warning=\"true\"", html)
        self.assertIn("Visible rows:", html)

    def test_html_preview_unmapped_keys_only_shows_potentially_mappable_keys(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            unmapped_source_keys=[
                "ContactInfo",
                "SupportsMonochrome",
                "Version",
                "ParametricShadows",
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("Unmapped Keys</div><div class=\"value\">1</div>", html)
        self.assertIn("<li><code>ParametricShadows</code></li>", html)
        self.assertNotIn("<li><code>ContactInfo</code></li>", html)
        self.assertNotIn("<li><code>SupportsMonochrome</code></li>", html)
        self.assertNotIn("<li><code>Version</code></li>", html)

    def test_html_preview_renders_curve_output_with_visual(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="ToneCurvePV2012",
                    source_value=["0, 0", "64, 52", "180, 210", "255, 255"],
                    section="Luminance Curve",
                    key="LCurve",
                    value="1;0.000000;0.000000;0.250000;0.203922;0.705882;0.823529;1.000000;1.000000;",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("Curve (4 pts)", html)
        self.assertIn("class=\"curve-mini\"", html)
        self.assertIn("Raw values", html)

    def test_html_preview_rows_link_to_rawpedia_tool_docs(self) -> None:
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key="Highlights2012",
                    source_value=-40,
                    section="Shadows & Highlights",
                    key="HLCompression",
                    value="24",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("data-doc-url=\"https://rawpedia.rawtherapee.com/Shadows/Highlights\"", html)
        self.assertIn("tabindex=\"0\"", html)
        self.assertIn("role=\"link\"", html)
        self.assertIn("tr.row-link[data-doc-url]", html)
        self.assertIn("window.open(url, \"_blank\", \"noopener,noreferrer\")", html)

    def test_html_preview_truncates_long_source_key_but_keeps_full_title(self) -> None:
        long_source_key = "HueAdjustmentRed+HueAdjustmentOrange+HueAdjustmentYellow+HueAdjustmentGreen+HueAdjustmentAqua+HueAdjustmentBlue+HueAdjustmentPurple+HueAdjustmentMagenta"
        result = ConversionResult(
            input_file=Path("/tmp/sample.xmp"),
            input_format="xmp",
            profile="balanced",
            mapped_values=[
                MappedValue(
                    source_key=long_source_key,
                    source_value=12,
                    section="HSV Equalizer",
                    key="HCurve",
                    value="1;0.000000;0.500000;0.350000;0.350000;0.166667;0.511000;0.350000;0.350000;",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "preview.html"
            write_html_preview(result, html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn(f'title="{long_source_key}"', html)
        self.assertRegex(html, r'<code class="source-key" title="[^"]+">[^<]*\.\.\.[^<]*</code>')


if __name__ == "__main__":
    unittest.main()
