#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  cat <<EOF
Usage: ${0##*/}

Run the repository's local validation sequence: Nix formatting, ShellCheck, disk
selector fixtures, then every flake check including NixOS VM tests. Use
"just check-fast" when only the narrow non-VM checks are wanted.
EOF
  exit 0
fi
[[ $# -eq 0 ]] || {
  echo "error: ${0##*/} accepts no arguments (try --help)" >&2
  exit 2
}
nix fmt -- --check .
shellcheck provisioning/*.sh provisioning/lib/*.sh scripts/*.sh tests/e2e/*.sh pxe/build-pxe.sh tests/selector.sh
bash tests/selector.sh
bash tests/secrets.sh
bash tests/repository.sh
nix flake check --print-build-logs
