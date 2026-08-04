#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  echo "Usage: ${0##*/}  # verify generated and secret paths are ignored by Git"
  exit 0
fi
[[ $# -eq 0 ]] || exit 2

root=$(git rev-parse --show-toplevel)
cd "$root"
for path in result result-pxe .e2e/target.raw artifacts/discovery/report.json artifacts/sessions/example/metadata.json pxe/http-root/nixos/initrd pxe/generated/tftp/ipxe.efi secrets/compose.env local.env; do
  git check-ignore -q "$path" || {
    echo "expected ignored path is not ignored: $path" >&2
    exit 1
  }
done
git check-ignore -q application/.env.example && {
  echo "tracked environment example is unexpectedly ignored" >&2
  exit 1
}
for document in \
  README.md \
  docs/ARCHITECTURE.md \
  docs/PROVISIONING.md \
  docs/APPLICATION_OPERATIONS.md \
  docs/MONITORING.md \
  docs/TESTING.md \
  docs/ROADMAP.md; do
  [[ -f $document ]] || {
    echo "authoritative documentation is missing: $document" >&2
    exit 1
  }
done
obsolete_document=$(
  find . \
    -path './.git' -prune -o \
    -type f \( -iname '*plan*.md' -o -iname '*investigation*.md' -o -iname '*options*.md' \) \
    -print -quit
)
[[ -z $obsolete_document ]] || {
  echo "obsolete planning document should be consolidated into docs/ROADMAP.md: $obsolete_document" >&2
  exit 1
}
if rg --quiet 'app\.netdata\.cloud/agent\.tar\.gz' modules/device-monitoring.nix; then
  echo "Netdata dashboard must use the immutable Nixpkgs netdataCloud package" >&2
  exit 1
fi
echo "repository ignore tests passed"
