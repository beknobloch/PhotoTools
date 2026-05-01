#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/workflow_common.sh
source "$script_dir/../lib/workflow_common.sh"

skip_derivatives=0

usage() {
  cat <<'USAGE'
Usage: ingest_exports.sh [--root PATH] [--dry-run] [--skip-derivatives]

Ingest JPG/JPEG files from Exports/File_Drop into date buckets:
  Exports/YYYY/MM-DD/master/YYYYMMDD-HHMMSS_00000.jpg

Matching sidecars are moved when found:
  foo.jpg.out.pp3 -> <canonical>.jpg.out.pp3
  foo.jpg.pp3     -> <canonical>.jpg.pp3
  foo.pp3         -> <canonical>.jpg.pp3
USAGE
}

parse_args() {
  WORKFLOW_ROOT="$(pwd)"
  WORKFLOW_DRY_RUN=0
  skip_derivatives=0

  while (( $# > 0 )); do
    case "$1" in
      --root)
        if (( $# < 2 )); then
          echo "Error: --root requires a path argument." >&2
          exit 1
        fi
        WORKFLOW_ROOT="$2"
        shift 2
        ;;
      --dry-run|-n)
        WORKFLOW_DRY_RUN=1
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
        echo "Error: unknown argument '$1'" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  WORKFLOW_ROOT="$(abs_path "$WORKFLOW_ROOT")"
}

move_sidecars() {
  local src="$1"
  local dest="$2"

  local side_a="${src}.out.pp3"
  local side_b="${src}.pp3"
  local side_c="${src%.*}.pp3"

  if [[ -f "$side_a" ]]; then
    safe_move "$side_a" "${dest}.out.pp3" && sidecars_moved=$((sidecars_moved + 1))
  fi

  if [[ -f "$side_b" ]]; then
    safe_move "$side_b" "${dest}.pp3" && sidecars_moved=$((sidecars_moved + 1))
  fi

  if [[ "$side_c" != "$side_b" && -f "$side_c" ]]; then
    safe_move "$side_c" "${dest}.pp3" && sidecars_moved=$((sidecars_moved + 1))
  fi
}

parse_args "$@"
require_command exiftool

drop_dir="$WORKFLOW_ROOT/Exports/File_Drop"

bootstrap_directories

shopt -s nullglob
drop_files=(
  "$drop_dir"/*.jpg "$drop_dir"/*.JPG
  "$drop_dir"/*.jpeg "$drop_dir"/*.JPEG
)
shopt -u nullglob

if (( ${#drop_files[@]} == 0 )); then
  echo "No JPG/JPEG files found in $drop_dir."
  exit 0
fi

seen=0
moved=0
skipped=0
sidecars_moved=0

for src in "${drop_files[@]}"; do
  seen=$((seen + 1))
  bname="$(basename "$src")"
  echo "Processing export: $bname"

  ts="$(pick_timestamp_prefer_prefix "$src")"
  date8="${ts%%-*}"
  year="${date8:0:4}"
  mm="${date8:4:2}"
  dd="${date8:6:2}"

  day_dir="$WORKFLOW_ROOT/Exports/$year/$mm-$dd"
  master_dir="$day_dir/master"

  safe_mkdir "$day_dir"
  safe_mkdir "$master_dir"

  idx="$(next_index_any_jpeg "$master_dir" "$ts")"
  ext_lc="$(printf '%s' "${bname##*.}" | tr '[:upper:]' '[:lower:]')"
  dest="$master_dir/${ts}_${idx}.${ext_lc}"

  if safe_move "$src" "$dest"; then
    moved=$((moved + 1))
    move_sidecars "$src" "$dest"
  else
    skipped=$((skipped + 1))
  fi
done

echo
echo "Done ingesting exports."
if (( WORKFLOW_DRY_RUN == 1 )); then
  echo "Mode: dry-run"
else
  echo "Mode: apply"
fi

echo "Files seen:      $seen"
echo "Masters moved:   $moved"
echo "Masters skipped: $skipped"
echo "Sidecars moved:  $sidecars_moved"

if (( skip_derivatives == 0 )); then
  echo
  echo "Generating derivatives..."
  derivative_args=(--root "$WORKFLOW_ROOT")
  if (( WORKFLOW_DRY_RUN == 1 )); then
    derivative_args+=(--dry-run)
  fi
  "$script_dir/generate_derivatives.sh" "${derivative_args[@]}"
fi
