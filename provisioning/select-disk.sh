#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=${PROJECT_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}
# shellcheck source=provisioning/lib/common.sh
source "$ROOT/provisioning/lib/common.sh"
# shellcheck source=provisioning/lib/disks.sh
source "$ROOT/provisioning/lib/disks.sh"

usage() {
  cat <<EOF
Usage: ${0##*/} [--disk /dev/disk/by-id/...] REPORT.json

Apply the repository's fail-closed disk policy to discovery JSON. With no --disk,
exactly one safe candidate must remain. With --disk, that stable path must itself
pass every safety exclusion.

Exclusions include removable, USB-transport, mounted, non-disk, unsupported, and
devices without a stable by-id link. The selected path is printed on stdout.

Options:
  --disk BY_ID  Explicit reviewed stable whole-disk path
  -h, --help    Show this help

Exit status is non-zero for zero or multiple candidates; this command never writes
to a block device.
EOF
}

requested=""
report=""
while (($#)); do
  case "$1" in
    --disk)
      requested=${2:?missing disk path}
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*) die "unknown option: $1" ;;
    *)
      [[ -z "$report" ]] || die "only one report is allowed"
      report=$1
      shift
      ;;
  esac
done
[[ -r "$report" ]] || die "discovery report is not readable: $report"
jq -e '.schema_version == "1.0"' "$report" >/dev/null || die "unsupported discovery schema"
candidates=$(safe_candidates "$report")

if [[ -n "$requested" ]]; then
  [[ "$requested" == /dev/disk/by-id/* ]] || die "--disk must use /dev/disk/by-id/..."
  matches=$(jq --arg path "$requested" '[.[] | select(.stable_path == $path)] | length' <<<"$candidates")
  ((matches == 1)) || die "explicit disk is absent or fails the safety policy: $requested"
  printf '%s\n' "$requested"
  exit 0
fi

count=$(jq 'length' <<<"$candidates")
case "$count" in
  1) jq -r '.[0].stable_path' <<<"$candidates" ;;
  0) die "no safe internal disk candidate remains; supply no disk until discovery is reviewed" ;;
  *) die "$count safe candidates remain; rerun with --disk and a reviewed full by-id path" ;;
esac
