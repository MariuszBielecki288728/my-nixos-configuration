#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  cat <<EOF
Usage: ${0##*/}

Run deterministic disk-selector fixture tests. This test reads JSON files only and
never accesses host block devices.
EOF
  exit 0
fi
[[ $# -eq 0 ]] || {
  echo "error: ${0##*/} accepts no arguments (try --help)" >&2
  exit 2
}

ROOT=${PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
selector="$ROOT/provisioning/select-disk.sh"
fixtures="$ROOT/tests/fixtures"

actual=$(PROJECT_ROOT="$ROOT" bash "$selector" "$fixtures/one-disk.json")
[[ "$actual" == "/dev/disk/by-id/ata-Safe_SSD_SERIAL" ]]

if PROJECT_ROOT="$ROOT" bash "$selector" "$fixtures/two-disks.json" >/dev/null 2>&1; then
  echo "ambiguous selection unexpectedly succeeded" >&2
  exit 1
fi

actual=$(PROJECT_ROOT="$ROOT" bash "$selector" --disk /dev/disk/by-id/nvme-SSD_B "$fixtures/two-disks.json")
[[ "$actual" == "/dev/disk/by-id/nvme-SSD_B" ]]

if PROJECT_ROOT="$ROOT" bash "$selector" --disk /dev/disk/by-id/ata-not-present "$fixtures/one-disk.json" >/dev/null 2>&1; then
  echo "invalid explicit disk unexpectedly succeeded" >&2
  exit 1
fi

if PROJECT_ROOT="$ROOT" bash "$selector" "$fixtures/mounted-disk.json" >/dev/null 2>&1; then
  echo "mounted disk unexpectedly succeeded" >&2
  exit 1
fi

echo "disk selector tests passed"
