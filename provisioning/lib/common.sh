#!/usr/bin/env bash
set -Eeuo pipefail

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '%s\n' "$*" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command is unavailable: $1"
}

project_root() {
  if [[ -n "${PROJECT_ROOT:-}" ]]; then
    printf '%s\n' "$PROJECT_ROOT"
  else
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd
  fi
}

cleanup_dir() {
  [[ -z "${1:-}" || ! -d "$1" ]] || rm -rf -- "$1"
}
