#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} [OUTPUT_DIRECTORY]

Build the pinned PXE bundle and copy its generated HTTP and TFTP roots into an
operator-controlled directory (default: pxe/generated). Existing output is never
overwritten. This command does not configure DHCP, DNS, or a router.
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
output=${1:-pxe/generated}
[[ ! -e "$output" ]] || {
  echo "error: refusing to overwrite $output; remove it explicitly first" >&2
  exit 1
}
nix build .#pxe-bundle --out-link result-pxe
mkdir -p "$output"
cp -R --no-preserve=mode,ownership result-pxe/. "$output/"
echo "PXE HTTP/TFTP roots and manifest written to $output"
