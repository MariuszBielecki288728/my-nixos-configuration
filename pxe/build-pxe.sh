#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} [OUTPUT_DIRECTORY]

Build the pinned PXE bundle and copy its nixos/ tree into an operator-controlled
HTTP root (default: pxe/http-root). Existing output is never overwritten; remove it
explicitly after review. This command does not configure DHCP, DNS, or a router.
EOF
}
[[ ${1:-} != -h && ${1:-} != --help ]] || {
  usage
  exit 0
}
[[ $# -le 1 ]] || {
  usage >&2
  exit 2
}
output=${1:-pxe/http-root}
[[ ! -e "$output/nixos" ]] || {
  echo "error: refusing to overwrite $output/nixos; remove it explicitly first" >&2
  exit 1
}
nix build .#pxe-bundle --out-link result-pxe
mkdir -p "$output"
cp -R --no-preserve=mode,ownership result-pxe/nixos "$output/nixos"
echo "PXE bundle written to $output/nixos"
