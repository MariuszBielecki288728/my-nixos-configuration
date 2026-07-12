#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  cat <<EOF
Usage: ${0##*/} [E2E_DIRECTORY]

Internal E2E cleanup helper. Stops the recorded QEMU process and copies only the
serial log and discovery report into E2E_DIRECTORY/logs for CI artifacts.
EOF
  exit 0
fi
[[ $# -le 1 ]] || {
  echo "error: too many arguments (try --help)" >&2
  exit 2
}

directory=${1:-.e2e}
mkdir -p "$directory/logs"
if [[ -f "$directory/pid" ]] && kill -0 "$(<"$directory/pid")" 2>/dev/null; then
  kill "$(<"$directory/pid")" || true
fi
cp -f "$directory/qemu.log" "$directory/logs/qemu.log" 2>/dev/null || true
cp -f "$directory/discovery.json" "$directory/logs/discovery.json" 2>/dev/null || true
