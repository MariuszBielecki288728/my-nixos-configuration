#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} PUBLIC_KEY_FILE

Build the rescue ISO with one public SSH key authorized for temporary root access.
A temporary wrapper flake injects the key without editing tracked configuration.
The resulting ISO path is printed on stdout and linked through ./result.

PUBLIC_KEY_FILE must contain an OpenSSH public key, never a private key.
Example: ${0##*/} ~/.ssh/id_ed25519.pub
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
key_file=$1
[[ -r "$key_file" ]] || {
  echo "error: public key file is not readable" >&2
  exit 1
}
public_key=$(head -1 "$key_file")
grep -Eq '^ssh-(ed25519|rsa|ecdsa-[^ ]+) [A-Za-z0-9+/=]+' <<<"$public_key" || {
  echo "error: file does not contain an OpenSSH public key" >&2
  exit 1
}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
# JSON string encoding is also valid Nix string syntax and avoids hand escaping keys.
key_nix=$(jq -Rn --arg value "$public_key" '$value')
base_url=$(jq -Rn --arg value "path:$root" '$value')
printf '%s\n' \
  '{' \
  "  inputs.base.url = $base_url;" \
  '  outputs = { base, ... }: {' \
  '    packages.x86_64-linux.default = (base.nixosConfigurations.rescue-iso.extendModules {' \
  '      modules = [ ./key.nix ];' \
  '    }).config.system.build.isoImage;' \
  '  };' \
  '}' >"$tmp/flake.nix"
printf '%s\n' '{' "  my.rescue.authorizedKeys = [ $key_nix ];" '}' >"$tmp/key.nix"
nix build "path:$tmp" --out-link result --print-build-logs
iso=$(find -L result/iso -maxdepth 1 -type f -name '*.iso' -print -quit)
[[ -n "$iso" ]] || {
  echo "error: ISO output is missing" >&2
  exit 1
}
readlink -f "$iso"
