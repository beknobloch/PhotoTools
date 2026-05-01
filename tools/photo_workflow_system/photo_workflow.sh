#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'USAGE'
Photo Workflow System

Usage:
  photo_workflow.sh <command> [options]
  photo_workflow.sh run [options]

Commands:
  run                  Initialize folders, ingest originals, ingest exports.
  init                 Create base folder structure only.
  ingest-originals     Sort RAW files from Originals/Ingest.
  ingest-exports       Sort JPG/JPEG files from Exports/File_Drop.
  normalize-exports    Rename export masters + linked print/web/sidecars.
  generate-derivatives Build print/web derivatives for masters.
  help                 Show this help.

Shared options:
  --root PATH          Workflow root (default: current directory).
  --dry-run, -n        Preview changes without writing files.

Command-specific options:
  run, ingest-exports:
    --skip-derivatives Skip derivative generation after export ingest.
USAGE
}

if (( $# == 0 )); then
  set -- run
fi

cmd="$1"
shift || true

run_op() {
  local op="$1"
  shift
  "$script_dir/operations/$op" "$@"
}

case "$cmd" in
  run)
    # Parse run-specific options so we can split arguments by operation.
    root_args=()
    dry_run=0
    skip_derivatives=0

    while (( $# > 0 )); do
      case "$1" in
        --root)
          if (( $# < 2 )); then
            echo "Error: --root requires a path argument." >&2
            exit 1
          fi
          root_args=(--root "$2")
          shift 2
          ;;
        --dry-run|-n)
          dry_run=1
          shift
          ;;
        --skip-derivatives)
          skip_derivatives=1
          shift
          ;;
        -h|--help)
          usage
          exit 0
          ;;
        *)
          echo "Error: unknown option for run: $1" >&2
          usage >&2
          exit 1
          ;;
      esac
    done

    common_args=("${root_args[@]}")
    if (( dry_run == 1 )); then
      common_args+=(--dry-run)
    fi

    echo "Step 1/3: initialize layout"
    run_op init_layout.sh "${common_args[@]}"

    echo
    echo "Step 2/3: ingest originals"
    run_op ingest_originals.sh "${common_args[@]}"

    echo
    echo "Step 3/3: ingest exports"
    export_args=("${common_args[@]}")
    if (( skip_derivatives == 1 )); then
      export_args+=(--skip-derivatives)
    fi
    run_op ingest_exports.sh "${export_args[@]}"
    ;;
  init)
    run_op init_layout.sh "$@"
    ;;
  ingest-originals)
    run_op ingest_originals.sh "$@"
    ;;
  ingest-exports)
    run_op ingest_exports.sh "$@"
    ;;
  normalize-exports)
    run_op normalize_exports.sh "$@"
    ;;
  generate-derivatives)
    run_op generate_derivatives.sh "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Error: unknown command '$cmd'." >&2
    usage >&2
    exit 1
    ;;
esac
