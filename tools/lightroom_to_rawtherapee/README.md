# Lightroom (.xmp/.dng) -> RawTherapee (.pp3)

`lr2rt` is a configurable converter that maps Adobe Lightroom preset metadata into RawTherapee profile files.

## Why this tool exists

Direct translation between Lightroom and RawTherapee settings is approximate. This tool is built around:

- A modular mapping engine (profiles + transforms)
- Config overrides without changing code
- A preview mode for before/after settings inspection
- Optional HTML report for quick comparison and tuning
- Centralized min/default/max value ranges for mapped RawTherapee outputs

## Features

- Supports input files:
  - `.xmp` Lightroom preset files
  - `.dng` mobile presets (extracts embedded XMP packet)
- Writes `.pp3` output
- Supports mapping profiles (`balanced`, `conservative`, `aggressive`)
- Includes broader default mapping coverage for:
  - exposure/highlights/shadows/white balance
  - clarity/texture/dehaze
  - vibrance/saturation
  - sharpening and denoising controls
  - Lightroom tone curves (`ToneCurvePV2012*`) to `RGB Curves`
  - Lightroom HSL sliders to `HSV Equalizer` curve approximations
  - Lightroom parametric tone controls to `ToneEqualizer` bands/pivot (heuristic)
- split toning to `ColorToning`
- vignette, distortion, perspective, and defringing basics
- range-aware output clamping based on a central RawTherapee value catalog
- HTML preview range visualization for numeric values (disabled slider + min/default/max labels)
- Provides warning and coverage feedback:
  - missing source keys
  - defaults applied
  - unmapped source metadata keys

## Install / run

From repo root:

```bash
cd tools/lightroom_to_rawtherapee
python3 -m pip install -e .
```

Or run module directly without install:

```bash
cd tools/lightroom_to_rawtherapee
python3 -m lr2rt --help
```

Optional GUI drag-and-drop support:

```bash
python3 -m pip install -e ".[gui]"
```

## Usage

List profiles:

```bash
python3 -m lr2rt profiles
```

Preview conversion (defaults to `balanced`):

```bash
python3 -m lr2rt preview /path/to/preset.xmp
```

Preview with HTML report:

```bash
python3 -m lr2rt preview /path/to/preset.xmp --html-report ./preview.html
```

Preview while merging into an existing RawTherapee profile template:

```bash
python3 -m lr2rt preview /path/to/preset.xmp --base-pp3 "/path/to/existing_profile.pp3"
```

Convert and write `.pp3` (defaults to `balanced`):

```bash
python3 -m lr2rt convert /path/to/preset.xmp ./output.pp3
```

Convert with a different profile:

```bash
python3 -m lr2rt convert /path/to/preset.xmp ./output.pp3 --profile aggressive
```

Open the simple desktop UI (drag `.xmp/.dng`, choose output folder, choose profile, preview, convert):

```bash
python3 -m lr2rt gui
```

Or:

```bash
lr2rt-gui
```

In GUI mode, `Preview HTML` overwrites a single file at `~/.lr2rt/gui_preview.html` and opens it in your default browser.

Convert using a known-good base profile (recommended for compatibility):

```bash
python3 -m lr2rt convert /path/to/preset.xmp ./output.pp3 --base-pp3 "/path/to/existing_profile.pp3"
```

`--base-pp3-mode` controls merge behavior:

- `safe` (default): keeps template compatibility structure but replaces converter-owned sections and disables untouched enabled tools, to avoid inheriting the template look.
- `preserve`: keeps all template values and only overrides mapped keys.

Example preserve mode:

```bash
python3 -m lr2rt convert /path/to/preset.xmp ./output.pp3 --base-pp3 "/path/to/existing_profile.pp3" --base-pp3-mode preserve
```

Dry run conversion (no file write):

```bash
python3 -m lr2rt convert /path/to/preset.dng --dry-run
```

## Mapping customization

Default mappings live in:

- `lr2rt/mappings/default_mapping.json`
- `lr2rt/mappings/rawtherapee_ranges.json` (central min/default/max value ranges)

Create an override JSON and pass it with `--mapping-file`:

```bash
python3 -m lr2rt convert input.xmp out.pp3 --mapping-file ./my_mapping_overrides.json
```

Overrides are deep-merged into defaults, so you can customize only the profile fields you need.

Default profiles are translation-focused (not look presets). If you want creative styling, add it in an override profile JSON.

## Project structure

- `lr2rt/parsers/`: `.xmp` and `.dng` metadata extraction
- `lr2rt/mapper.py`: transform and target mapping pipeline
- `lr2rt/pp3_template.py`: parse and merge against existing `.pp3` templates
- `lr2rt/pp3_writer.py`: `.pp3` serialization
- `lr2rt/reporting/preview.py`: terminal + HTML preview report
- `tests/`: fixtures and unit tests

## Notes and limitations

- Mapping is intentionally heuristic. Use `preview` to tune profile behavior.
- Numeric target values are range-clamped using `rawtherapee_ranges.json` unless a mapping sets `skip_target_range_clamp: true`.
- White balance writes `White Balance/Green` in `.pp3`; RawTherapee's UI tint control can present this differently from the stored value scale.
- Many mappings are marked optional so absent Lightroom keys do not produce warning spam.
- `.dng` support currently parses embedded XMP packets by scanning file bytes.
- Not every Lightroom parameter has a direct RawTherapee equivalent.
- RawTherapee key names can vary by version; `--base-pp3` preserves full profile structure and tends to apply more reliably.
