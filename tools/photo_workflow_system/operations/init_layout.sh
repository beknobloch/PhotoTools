#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/workflow_common.sh
source "$script_dir/../lib/workflow_common.sh"

usage() {
  cat <<'USAGE'
Usage: init_layout.sh [--root PATH] [--dry-run]

Create the primary workflow directories:
  Originals/
  Originals/Ingest/
  Exports/
  Exports/File_Drop/
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

parse_common_options "$@"

if (( WORKFLOW_DRY_RUN == 1 )); then
  echo "[DRY-RUN] Initializing layout in $WORKFLOW_ROOT"
else
  echo "Initializing layout in $WORKFLOW_ROOT"
fi

bootstrap_directories
