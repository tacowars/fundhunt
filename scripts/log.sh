#!/bin/bash
# Decision-record helper — scaffolds docs/log/YYYY-MM-DD-<slug>.md
# (convention: docs/log/README.md).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

LOG_DIR=docs/log

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/log.sh new [--date YYYY-MM-DD] <slug> [title...]
                                              Create docs/log/<date>-<slug>.md
                                              (date defaults to today; --date is
                                              for post-hoc records)
  bash scripts/log.sh list                    List records, newest first
EOF
  exit 1
}

die() { echo "log.sh: $*" >&2; exit 1; }

cmd_new() {
  local date=""
  if [ "${1:-}" = --date ]; then
    [ $# -ge 2 ] || usage
    date=$2; shift 2
    [[ $date =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
      || die "--date must be YYYY-MM-DD (got '$date')"
  fi
  [ $# -ge 1 ] || usage
  local slug=$1; shift
  [[ $slug =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]] \
    || die "slug must be kebab-case (got '$slug')"
  local file title
  [ -n "$date" ] || date=$(date +%F)
  file="$LOG_DIR/$date-$slug.md"
  [ -e "$file" ] && die "$file already exists — pick a different slug"
  if [ $# -ge 1 ]; then title="$*"; else title="${slug//-/ }"; fi
  cat >"$file" <<EOF
# $title

- Date: $date
- Links: <issue #n · PR #n · ADR <slug> — whichever apply>

## Decision

## Why

## Punted / alternatives
EOF
  echo "$file"
}

cmd_list() {
  ls -1r "$LOG_DIR" | grep -E '^[0-9]{4}-' | while read -r f; do
    printf '%s  %s\n' "$f" "$(sed -n 's/^# //p;1q' "$LOG_DIR/$f")"
  done
}

case "${1:-}" in
  new)  shift; cmd_new "$@" ;;
  list) shift; cmd_list ;;
  *)    usage ;;
esac
