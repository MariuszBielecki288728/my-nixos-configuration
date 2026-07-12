#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=${PROJECT_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}
# shellcheck source=provisioning/lib/common.sh
source "$ROOT/provisioning/lib/common.sh"
# shellcheck source=provisioning/lib/remote.sh
source "$ROOT/provisioning/lib/remote.sh"
# shellcheck source=provisioning/lib/disks.sh
source "$ROOT/provisioning/lib/disks.sh"

usage() {
  cat <<EOF
Usage: ${0##*/} [OPTIONS] user@host

Collect a read-only JSON hardware report over SSH. The remote command reads DMI,
lsblk/by-id, mount, interface, PCI, and USB data; it does not modify the host.

Options:
  --output FILE    Report path (default: timestamped artifacts/discovery/*.json)
  --port PORT      SSH port (default: 22)
  --identity FILE  Local private SSH identity
  -h, --help       Show this help

The report is written mode 0600. Its path is printed on stdout; candidate summaries
go to stderr so callers can safely capture the path.

Example:
  nix run .#discover -- --identity ~/.ssh/id_ed25519 root@nixos-rescue.local
EOF
}

output=""
port=22
identity_file=""
target=""
while (($#)); do
  case "$1" in
    --output)
      output=${2:?missing output path}
      shift 2
      ;;
    --port)
      port=${2:?missing port}
      shift 2
      ;;
    --identity)
      identity_file=${2:?missing identity file}
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*) die "unknown option: $1" ;;
    *)
      [[ -z "$target" ]] || die "only one SSH target is allowed"
      target=$1
      shift
      ;;
  esac
done
[[ -n "$target" ]] || {
  usage >&2
  exit 2
}
[[ "$port" =~ ^[0-9]+$ ]] || die "port must be numeric"
[[ -z "$identity_file" || -r "$identity_file" ]] || die "identity file is not readable: $identity_file"
require_command jq
require_command ssh

if [[ -z "$output" ]]; then
  mkdir -p artifacts/discovery
  safe_target=${target//@/_}
  safe_target=${safe_target//[^a-zA-Z0-9._-]/_}
  output="artifacts/discovery/$(date -u +%Y%m%dT%H%M%SZ)-${safe_target}.json"
else
  mkdir -p "$(dirname -- "$output")"
fi

tmp=$(mktemp)
trap 'rm -f -- "$tmp"' EXIT

# Keep the collector self-contained so delivery by ISO, PXE, or QEMU behaves alike.
run_ssh "$target" "$port" "$identity_file" 'bash -s' >"$tmp" <<'REMOTE'
set -Eeuo pipefail
read_optional() { [[ -r "$1" ]] && tr -d '\n' <"$1" || true; }
by_id=$(find /dev/disk/by-id -maxdepth 1 -type l -printf '%p\n' 2>/dev/null | while IFS= read -r link; do
  jq -n --arg path "$link" --arg target "$(readlink -f -- "$link")" '{path:$path,target:$target}'
done | jq -s '.')
jq -n \
  --arg schema_version "1.0" \
  --arg collected_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg hostname "$(hostname)" \
  --arg vendor "$(read_optional /sys/class/dmi/id/sys_vendor)" \
  --arg product_name "$(read_optional /sys/class/dmi/id/product_name)" \
  --arg product_version "$(read_optional /sys/class/dmi/id/product_version)" \
  --argjson block_devices "$(lsblk --json --bytes --output NAME,PATH,SIZE,MODEL,SERIAL,TRAN,RM,ROTA,TYPE,FSTYPE,MOUNTPOINTS)" \
  --argjson by_id "$by_id" \
  --argjson interfaces "$(ip -json address)" \
  --arg mounts "$(findmnt --json --bytes 2>/dev/null || printf '{"filesystems":[]}')" \
  --arg pci "$(lspci -nn 2>/dev/null || true)" \
  --arg usb "$(lsusb 2>/dev/null || true)" \
  '{schema_version:$schema_version,collected_at:$collected_at,hostname:$hostname,
    dmi:{vendor:$vendor,product_name:$product_name,product_version:$product_version},
    block_devices:$block_devices,by_id:$by_id,network_interfaces:$interfaces,
    mounts:($mounts|fromjson),pci_devices:($pci|split("\n")|map(select(length>0))),
    usb_devices:($usb|split("\n")|map(select(length>0)))}'
REMOTE

jq -e '.schema_version == "1.0" and (.block_devices.blockdevices | type == "array")' "$tmp" >/dev/null ||
  die "remote discovery returned invalid JSON"
install -m 0600 "$tmp" "$output"
log "Discovery report: $output"
candidates=$(safe_candidates "$output")
log "Safe disk candidates: $(jq 'length' <<<"$candidates")"
jq -r '.[] | "  \(.stable_path) | \(.model // "unknown") | \(.size) bytes"' <<<"$candidates" >&2
printf '%s\n' "$output"
