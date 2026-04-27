from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from lr2rt.gui import (
    ConversionQueueModel,
    GuiPreferences,
    build_output_path,
    build_preview_path,
    is_supported_input,
    load_gui_preferences,
    parse_drop_paths,
    run_gui_conversion_checked,
    run_gui_preview,
    save_gui_preferences,
)

FIXTURE_XMP = Path(__file__).parent / "fixtures" / "sample_preset.xmp"


def _write_warning_mapping(path: Path) -> Path:
    override = {
        "profiles": {
            "strict_test": {
                "description": "Produces warning for strict mode tests.",
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

    def test_gui_preferences_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prefs_path = Path(tmp_dir) / "prefs.json"
            preferences = GuiPreferences(
                input_dir="/tmp/in",
                output_dir="/tmp/out",
                profile="aggressive",
                base_pp3="/tmp/base.pp3",
                base_pp3_mode="preserve",
                strict=True,
            )
            save_gui_preferences(preferences, path=prefs_path)
            loaded = load_gui_preferences(path=prefs_path)

        self.assertEqual(loaded.input_dir, preferences.input_dir)
        self.assertEqual(loaded.output_dir, preferences.output_dir)
        self.assertEqual(loaded.profile, preferences.profile)
        self.assertEqual(loaded.base_pp3, preferences.base_pp3)
        self.assertEqual(loaded.base_pp3_mode, preferences.base_pp3_mode)
        self.assertEqual(loaded.strict, preferences.strict)

    def test_gui_preferences_invalid_file_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prefs_path = Path(tmp_dir) / "prefs.json"
            prefs_path.write_text("{not-json", encoding="utf-8")
            loaded = load_gui_preferences(path=prefs_path)

        self.assertEqual(loaded.base_pp3_mode, "safe")
        self.assertEqual(loaded.profile, "balanced")
        self.assertFalse(loaded.strict)

    def test_run_gui_preview_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "preview.html"
            preview_path, result = run_gui_preview(FIXTURE_XMP, preview_path=output)
            html = preview_path.read_text(encoding="utf-8")

        self.assertEqual(preview_path, output.resolve())
        self.assertEqual(result.input_file, FIXTURE_XMP.resolve())
        self.assertIn("lr2rt Conversion Preview", html)
        self.assertIn("RawTherapee Target", html)

    def test_queue_model_add_remove_clear_handles_mixed_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            valid_xmp = tmp_path / "a.xmp"
            valid_dng = tmp_path / "b.dng"
            unsupported = tmp_path / "c.pp3"
            missing = tmp_path / "missing.xmp"

            valid_xmp.write_text("", encoding="utf-8")
            valid_dng.write_text("", encoding="utf-8")
            unsupported.write_text("", encoding="utf-8")

            queue = ConversionQueueModel()
            summary = queue.add_paths([valid_xmp, unsupported, missing, valid_xmp])
            second_summary = queue.add_paths([valid_dng])

            self.assertEqual(summary.added, 1)
            self.assertEqual(summary.skipped_unsupported, 1)
            self.assertEqual(summary.skipped_missing, 1)
            self.assertEqual(summary.skipped_duplicate, 1)
            self.assertEqual(second_summary.added, 1)
            self.assertEqual(len(queue), 2)

            removed = queue.remove_indices([0])
            self.assertEqual(removed, 1)
            self.assertEqual(len(queue), 1)

            queue.clear()
            self.assertEqual(len(queue), 0)

    def test_batch_conversion_in_strict_mode_fails_rows_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_a = tmp_path / "a.xmp"
            input_b = tmp_path / "b.xmp"
            input_a.write_text(FIXTURE_XMP.read_text(encoding="utf-8"), encoding="utf-8")
            input_b.write_text(FIXTURE_XMP.read_text(encoding="utf-8"), encoding="utf-8")

            output_dir = tmp_path / "out"
            mapping_path = _write_warning_mapping(tmp_path / "override.json")

            outcome_a = run_gui_conversion_checked(
                input_path=input_a,
                output_dir=output_dir,
                profile="strict_test",
                mapping_file=str(mapping_path),
                strict=True,
            )
            outcome_b = run_gui_conversion_checked(
                input_path=input_b,
                output_dir=output_dir,
                profile="strict_test",
                mapping_file=str(mapping_path),
                strict=True,
            )

        self.assertTrue(outcome_a[2].failed)
        self.assertTrue(outcome_b[2].failed)
        self.assertGreater(len(outcome_a[1].warnings), 0)
        self.assertGreater(len(outcome_b[1].warnings), 0)
        self.assertIsNone(outcome_a[0])
        self.assertIsNone(outcome_b[0])
        self.assertFalse((output_dir / "a.pp3").exists())
        self.assertFalse((output_dir / "b.pp3").exists())

    def test_batch_conversion_without_strict_writes_outputs_even_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_file = tmp_path / "a.xmp"
            input_file.write_text(FIXTURE_XMP.read_text(encoding="utf-8"), encoding="utf-8")

            output_dir = tmp_path / "out"
            mapping_path = _write_warning_mapping(tmp_path / "override.json")

            output_path, result, strict_eval = run_gui_conversion_checked(
                input_path=input_file,
                output_dir=output_dir,
                profile="strict_test",
                mapping_file=str(mapping_path),
                strict=False,
            )
            output_exists = (output_dir / "a.pp3").exists()

        self.assertFalse(strict_eval.failed)
        self.assertGreater(len(result.warnings), 0)
        self.assertIsNotNone(output_path)
        self.assertTrue(output_exists)


if __name__ == "__main__":
    unittest.main()
