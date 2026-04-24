from pathlib import Path
import tempfile
import unittest

from lr2rt.gui import build_output_path, build_preview_path, is_supported_input, parse_drop_paths, run_gui_preview

FIXTURE_XMP = Path(__file__).parent / "fixtures" / "sample_preset.xmp"


class GuiHelperTests(unittest.TestCase):
    def test_is_supported_input(self) -> None:
        self.assertTrue(is_supported_input(Path("/tmp/a.xmp")))
        self.assertTrue(is_supported_input(Path("/tmp/b.dng")))
        self.assertFalse(is_supported_input(Path("/tmp/c.pp3")))

    def test_build_output_path_uses_input_stem(self) -> None:
        output = build_output_path(Path("/tmp/my preset.xmp"), Path("/tmp/out"))
        self.assertEqual(output, Path("/tmp/out/my preset.pp3"))

    def test_parse_drop_paths_handles_braced_paths_with_spaces(self) -> None:
        data = "{/tmp/a b.xmp} {/tmp/c.dng}"
        paths = parse_drop_paths(data)
        self.assertEqual(paths, [Path("/tmp/a b.xmp").resolve(), Path("/tmp/c.dng").resolve()])

    def test_build_preview_path_uses_stable_filename(self) -> None:
        self.assertEqual(build_preview_path().name, "gui_preview.html")

    def test_run_gui_preview_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "preview.html"
            preview_path, result = run_gui_preview(FIXTURE_XMP, preview_path=output)
            html = preview_path.read_text(encoding="utf-8")

        self.assertEqual(preview_path, output.resolve())
        self.assertEqual(result.input_file, FIXTURE_XMP.resolve())
        self.assertIn("lr2rt Conversion Preview", html)
        self.assertIn("RawTherapee Target", html)


if __name__ == "__main__":
    unittest.main()
