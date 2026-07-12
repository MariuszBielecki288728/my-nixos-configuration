#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} ISO

Inspect an ISO without mounting or modifying it. Prints detected file type, SHA-256
checksum, and human-readable size for verification before writing or publishing.
EOF
}
[[ ${1:-} != -h && ${1:-} != --help ]] || {
  usage
  exit 0
}
[[ $# -eq 1 ]] || {
  usage >&2
  exit 2
}
iso=$1
[[ -f "$iso" ]] || {
  echo "error: ISO not found: $iso" >&2
  exit 1
}
file "$iso"
sha256sum "$iso"
du -h "$iso"
