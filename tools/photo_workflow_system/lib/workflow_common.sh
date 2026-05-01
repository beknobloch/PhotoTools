#!/usr/bin/env bash

set -euo pipefail

WORKFLOW_ROOT=""
WORKFLOW_DRY_RUN=0

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command not found: $cmd" >&2
    exit 1
  fi
}

abs_path() {
  local target="$1"
  if [[ "$target" = /* ]]; then
    printf '%s\n' "$target"
    return
  fi

  if [[ "$target" == "." ]]; then
    pwd
    return
  fi

  printf '%s/%s\n' "$(pwd)" "$target"
}

parse_common_options() {
  WORKFLOW_ROOT="$(pwd)"
  WORKFLOW_DRY_RUN=0

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
      --)
        shift
        break
        ;;
      *)
        break
        ;;
    esac
  done

  WORKFLOW_ROOT="$(abs_path "$WORKFLOW_ROOT")"

  if (( $# > 0 )); then
    echo "Error: unknown arguments: $*" >&2
    exit 1
  fi
}

bootstrap_directories() {
  safe_mkdir "$WORKFLOW_ROOT/Originals"
  safe_mkdir "$WORKFLOW_ROOT/Originals/Ingest"
  safe_mkdir "$WORKFLOW_ROOT/Exports"
  safe_mkdir "$WORKFLOW_ROOT/Exports/File_Drop"
}

safe_mkdir() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    return
  fi

  if (( WORKFLOW_DRY_RUN == 1 )); then
    echo "  would create dir: ${dir#"$WORKFLOW_ROOT"/}"
  else
    mkdir -p "$dir"
    echo "  created dir: ${dir#"$WORKFLOW_ROOT"/}"
  fi
}

safe_move() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    return 1
  fi

  if [[ -e "$dst" ]]; then
    echo "  skip (target exists): $(basename "$src") -> $(basename "$dst")"
    return 1
  fi

  if (( WORKFLOW_DRY_RUN == 1 )); then
    echo "  would move: ${src#"$WORKFLOW_ROOT"/} -> ${dst#"$WORKFLOW_ROOT"/}"
  else
    mv -- "$src" "$dst"
    echo "  moved: ${src#"$WORKFLOW_ROOT"/} -> ${dst#"$WORKFLOW_ROOT"/}"
  fi

  return 0
}

pick_timestamp_from_file() {
  local file="$1"
  local ts=""

  ts="$(exiftool -s -s -s -d '%Y%m%d-%H%M%S' -CreateDate "$file" 2>/dev/null || true)"
  if [[ -z "$ts" ]]; then
    ts="$(exiftool -s -s -s -d '%Y%m%d-%H%M%S' -DateTimeOriginal "$file" 2>/dev/null || true)"
  fi

  if [[ -z "$ts" ]]; then
    local mtime
    mtime="$(stat -f '%m' "$file")"
    ts="$(date -r "$mtime" '+%Y%m%d-%H%M%S')"
  fi

  printf '%s' "$ts"
}

pick_timestamp_prefer_prefix() {
  local file="$1"
  local base
  base="$(basename "$file")"

  if [[ "$base" =~ ^([0-9]{8}-[0-9]{6}) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
    return
  fi

  pick_timestamp_from_file "$file"
}

next_index_any_jpeg() {
  local dir="$1"
  local ts="$2"
  local i=0
  local idx
  local base

  while :; do
    printf -v idx '%05d' "$i"
    base="${dir}/${ts}_${idx}"
    if [[ ! -e "${base}.jpg" && ! -e "${base}.jpeg" ]]; then
      printf '%s' "$idx"
      return
    fi
    i=$((i + 1))
  done
}

next_index_for_ext() {
  local dir="$1"
  local ts="$2"
  local ext="$3"
  local i=0
  local idx

  while :; do
    printf -v idx '%05d' "$i"
    if [[ ! -e "${dir}/${ts}_${idx}.${ext}" ]]; then
      printf '%s' "$idx"
      return
    fi
    i=$((i + 1))
  done
}
