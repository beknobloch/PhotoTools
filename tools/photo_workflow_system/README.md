# Photo Workflow System

A filesystem-based workflow for organizing originals and exports with one entrypoint.

## Entrypoint

Run from anywhere:

```bash
/path/to/photo_workflow.sh run --root /path/to/photo-library
```

If the root is empty, this bootstraps:

- `Originals/`
- `Originals/Ingest/`
- `Exports/`
- `Exports/File_Drop/`

## Folder Model

- `Originals/Ingest`: Drop incoming `.NEF` / `.DNG` files here.
- `Originals/YYYY/MM-DD/raw`: Canonical originals destination.
- `Exports/File_Drop`: Drop final exported `.jpg/.jpeg` files here.
- `Exports/YYYY/MM-DD/master`: Canonical export masters destination.
- `Exports/YYYY/MM-DD/print`: Print derivatives.
- `Exports/YYYY/MM-DD/web`: Web derivatives.

## Commands

```bash
photo_workflow.sh run [--root PATH] [--dry-run] [--skip-derivatives]
photo_workflow.sh init [--root PATH] [--dry-run]
photo_workflow.sh ingest-originals [--root PATH] [--dry-run]
photo_workflow.sh ingest-exports [--root PATH] [--dry-run] [--skip-derivatives]
photo_workflow.sh normalize-exports [--root PATH] [--dry-run]
photo_workflow.sh generate-derivatives [--root PATH] [--dry-run]
```

## Requirements

- `bash`
- `exiftool` (timestamp extraction)
- `sips` (web derivative resizing)
- `magick` (print derivative canvas generation)

## Naming

Canonical names are timestamp-based:

- `YYYYMMDD-HHMMSS_00000.NEF`
- `YYYYMMDD-HHMMSS_00000.DNG`
- `YYYYMMDD-HHMMSS_00000.jpg`

Sidecars follow the same base when present.
