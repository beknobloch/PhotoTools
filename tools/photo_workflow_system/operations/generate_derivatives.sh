#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/workflow_common.sh
source "$script_dir/../lib/workflow_common.sh"

usage() {
  cat <<'USAGE'
Usage: generate_derivatives.sh [--root PATH] [--dry-run]

For each master JPG/JPEG in Exports/*/*/master, generate:
  print/<base>_print.<ext>
  web/<base>_web.<ext>
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

parse_common_options "$@"
require_command sips
require_command magick

bootstrap_directories

exports_root="$WORKFLOW_ROOT/Exports"

masters_seen=0
print_created=0
web_created=0
skipped=0

while IFS= read -r -d '' master_dir; do
  parent_dir="$(dirname "$master_dir")"
  print_dir="$parent_dir/print"
  web_dir="$parent_dir/web"

  while IFS= read -r -d '' src; do
    masters_seen=$((masters_seen + 1))

    name="$(basename "$src")"
    stem="${name%.*}"
    ext="${name##*.}"
    print_out="$print_dir/${stem}_print.${ext}"
    web_out="$web_dir/${stem}_web.${ext}"

    need_print=0
    need_web=0
    [[ ! -f "$print_out" ]] && need_print=1
    [[ ! -f "$web_out" ]] && need_web=1

    if [[ "$need_print" -eq 0 && "$need_web" -eq 0 ]]; then
      skipped=$((skipped + 1))
      continue
    fi

    safe_mkdir "$print_dir"
    safe_mkdir "$web_dir"

    rel="${src#"$WORKFLOW_ROOT"/}"
    if [[ "$need_print" -eq 1 && "$need_web" -eq 1 ]]; then
      echo "[MAKE_BOTH] $rel"
    elif [[ "$need_print" -eq 1 ]]; then
      echo "[MAKE_PRINT] $rel"
    else
      echo "[MAKE_WEB] $rel"
    fi

    if [[ "$need_print" -eq 1 ]]; then
      if (( WORKFLOW_DRY_RUN == 1 )); then
        echo "  would create: ${print_out#"$WORKFLOW_ROOT"/}"
      else
        read -r src_w src_h < <(
          sips -g pixelWidth -g pixelHeight "$src" 2>/dev/null |
            awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} END{print w, h}'
        )

        if [[ -z "${src_w:-}" || -z "${src_h:-}" ]]; then
          echo "Error: failed to read dimensions for $src" >&2
          exit 1
        fi

        left=$(( (src_w * 10 + 50) / 100 ))
        right=$left
        top=$(( (src_h * 10 + 50) / 100 ))
        bottom=$(( (src_h * 15 + 50) / 100 ))
        canvas_w=$(( src_w + left + right ))
        canvas_h=$(( src_h + top + bottom ))

        magick \
          -size "${canvas_w}x${canvas_h}" xc:white \
          "$src" -geometry "+${left}+${top}" -composite \
          -quality 95 \
          "$print_out"
      fi
      print_created=$((print_created + 1))
    fi

    if [[ "$need_web" -eq 1 ]]; then
      if (( WORKFLOW_DRY_RUN == 1 )); then
        echo "  would create: ${web_out#"$WORKFLOW_ROOT"/}"
      else
        sips \
          -Z 2048 \
          -s format jpeg \
          -s formatOptions 82 \
          "$src" \
          --out "$web_out" >/dev/null
      fi
      web_created=$((web_created + 1))
    fi
  done < <(
    find "$master_dir" -maxdepth 1 -type f \
      \( -iname '*.jpg' -o -iname '*.jpeg' \) \
      -print0
  )
done < <(find "$exports_root" -type d -name master -print0)

echo
echo "Done generating derivatives."
if (( WORKFLOW_DRY_RUN == 1 )); then
  echo "Mode: dry-run"
else
  echo "Mode: apply"
fi

echo "Masters scanned: $masters_seen"
echo "Print created:   $print_created"
echo "Web created:     $web_created"
echo "Skipped:         $skipped"
