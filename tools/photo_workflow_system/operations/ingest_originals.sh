#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/workflow_common.sh
source "$script_dir/../lib/workflow_common.sh"

usage() {
  cat <<'USAGE'
Usage: ingest_originals.sh [--root PATH] [--dry-run]

Ingest RAW files from Originals/Ingest into date buckets:
  Originals/YYYY/MM-DD/raw/YYYYMMDD-HHMMSS_00000.<EXT>

Supported RAW extensions: NEF, DNG.
Matching sidecars are moved when found:
  foo.NEF.pp3 -> <canonical>.NEF.pp3
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

parse_common_options "$@"
require_command exiftool

bootstrap_directories

ingest_dir="$WORKFLOW_ROOT/Originals/Ingest"

shopt -s nullglob
raw_files=(
  "$ingest_dir"/*.NEF "$ingest_dir"/*.nef
  "$ingest_dir"/*.DNG "$ingest_dir"/*.dng
)
shopt -u nullglob

if (( ${#raw_files[@]} == 0 )); then
  echo "No RAW files found in $ingest_dir."
  exit 0
fi

seen=0
moved=0
skipped=0
sidecars_moved=0

for src in "${raw_files[@]}"; do
  seen=$((seen + 1))
  name="$(basename "$src")"

  ext="${name##*.}"
  ext_upper="$(printf '%s' "$ext" | tr '[:lower:]' '[:upper:]')"
  if [[ "$ext_upper" != "NEF" && "$ext_upper" != "DNG" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  echo "Processing original: $name"

  ts="$(pick_timestamp_prefer_prefix "$src")"
  date8="${ts%%-*}"
  year="${date8:0:4}"
  mm="${date8:4:2}"
  dd="${date8:6:2}"

  day_dir="$WORKFLOW_ROOT/Originals/$year/$mm-$dd"
  raw_dir="$day_dir/raw"

  safe_mkdir "$day_dir"
  safe_mkdir "$raw_dir"

  idx="$(next_index_for_ext "$raw_dir" "$ts" "$ext_upper")"
  new_base="${ts}_${idx}.${ext_upper}"
  dest="$raw_dir/$new_base"

  if safe_move "$src" "$dest"; then
    moved=$((moved + 1))
    if [[ -f "${src}.pp3" ]]; then
      safe_move "${src}.pp3" "${dest}.pp3" && sidecars_moved=$((sidecars_moved + 1))
    fi
  else
    skipped=$((skipped + 1))
  fi
done

echo
echo "Done ingesting originals."
if (( WORKFLOW_DRY_RUN == 1 )); then
  echo "Mode: dry-run"
else
  echo "Mode: apply"
fi

echo "Files seen:      $seen"
echo "RAW moved:       $moved"
echo "RAW skipped:     $skipped"
echo "Sidecars moved:  $sidecars_moved"
