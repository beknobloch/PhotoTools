#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/workflow_common.sh
source "$script_dir/../lib/workflow_common.sh"

usage() {
  cat <<'USAGE'
Usage: normalize_exports.sh [--root PATH] [--dry-run]

Normalize names for export masters and linked files:
  master/<base>.jpg
  master/<base>.jpg.out.pp3
  master/<base>.jpg.pp3
  print/<base>_print.jpg
  web/<base>_web.jpg
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

parse_common_options "$@"
require_command exiftool

exports_root="$WORKFLOW_ROOT/Exports"
bootstrap_directories

masters_seen=0
master_renamed=0
linked_renamed=0
skipped=0

safe_rename_linked() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    return 0
  fi

  if [[ -e "$dst" ]]; then
    echo "  skip (target exists): $(basename "$src") -> $(basename "$dst")"
    return 0
  fi

  if (( WORKFLOW_DRY_RUN == 1 )); then
    echo "  would rename: $(basename "$src") -> $(basename "$dst")"
  else
    mv -- "$src" "$dst"
    echo "  renamed: $(basename "$src") -> $(basename "$dst")"
  fi

  linked_renamed=$((linked_renamed + 1))
}

while IFS= read -r -d '' master_dir; do
  parent_dir="$(dirname "$master_dir")"
  print_dir="$parent_dir/print"
  web_dir="$parent_dir/web"

  while IFS= read -r -d '' src; do
    masters_seen=$((masters_seen + 1))

    old_name="$(basename "$src")"
    old_base="${old_name%.*}"
    ext="${old_name##*.}"
    ext_lower="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"

    if [[ "$old_name" =~ ^[0-9]{8}-[0-9]{6}_[0-9]{5}\.[Jj][Pp][Ee]?[Gg]$ ]]; then
      new_base="$old_base"
      new_name="$old_name"
    else
      ts="$(pick_timestamp_from_file "$src")"
      idx="$(next_index_any_jpeg "$master_dir" "$ts")"
      new_base="${ts}_${idx}"
      new_name="${new_base}.${ext_lower}"
    fi

    rel="${src#"$WORKFLOW_ROOT"/}"

    if [[ "$old_name" == "$new_name" ]]; then
      echo "[KEEP] $rel"
      skipped=$((skipped + 1))
    else
      echo "[RENAME] $rel -> $new_name"
    fi

    safe_rename_linked "$master_dir/${old_name}.out.pp3" "$master_dir/${new_name}.out.pp3"
    safe_rename_linked "$master_dir/${old_name}.pp3" "$master_dir/${new_name}.pp3"

    safe_rename_linked "$print_dir/${old_base}_print.${ext_lower}" "$print_dir/${new_base}_print.${ext_lower}"
    safe_rename_linked "$print_dir/${old_base}.${ext_lower}" "$print_dir/${new_base}_print.${ext_lower}"

    safe_rename_linked "$web_dir/${old_base}_web.${ext_lower}" "$web_dir/${new_base}_web.${ext_lower}"
    safe_rename_linked "$web_dir/${old_base}.${ext_lower}" "$web_dir/${new_base}_web.${ext_lower}"

    if [[ "$old_name" != "$new_name" ]]; then
      if [[ -e "$master_dir/$new_name" ]]; then
        echo "  skip (target exists): $old_name -> $new_name"
      else
        if (( WORKFLOW_DRY_RUN == 1 )); then
          echo "  would rename: $old_name -> $new_name"
        else
          mv -- "$src" "$master_dir/$new_name"
          echo "  renamed: $old_name -> $new_name"
        fi
        master_renamed=$((master_renamed + 1))
      fi
    fi
  done < <(
    find "$master_dir" -maxdepth 1 -type f \
      \( -iname '*.jpg' -o -iname '*.jpeg' \) \
      -print0
  )
done < <(find "$exports_root" -type d -name master -print0)

echo
echo "Done normalizing exports."
if (( WORKFLOW_DRY_RUN == 1 )); then
  echo "Mode: dry-run"
else
  echo "Mode: apply"
fi

echo "Master files scanned:  $masters_seen"
echo "Master files renamed:  $master_renamed"
echo "Linked files renamed:  $linked_renamed"
echo "Skipped/kept:          $skipped"
