#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} ISO /dev/REMOVABLE_WHOLE_DEVICE

DESTRUCTIVE: write an ISO to a removable whole block device. The command rejects
partitions, non-removable devices, and common system-disk paths, prints lsblk details,
and requires typing the exact device path before dd starts.

Example: ${0##*/} result/iso/nixos-mini-pc-rescue.iso /dev/sdX
Never copy the example device name without reviewing lsblk output.
EOF
}
[[ ${1:-} != -h && ${1:-} != --help ]] || {
  usage
  exit 0
}
[[ $# -eq 2 ]] || {
  usage >&2
  exit 2
}
iso=$1
device=$2
[[ -f "$iso" ]] || {
  echo "error: ISO is not a regular file: $iso" >&2
  exit 1
}
[[ -b "$device" ]] || {
  echo "error: target is not a block device: $device" >&2
  exit 1
}
[[ "$device" != /dev/sda && "$device" != /dev/nvme0n1 ]] || {
  echo "error: refusing a common system-disk path without a project code change" >&2
  exit 1
}
type=$(lsblk -dn -o TYPE "$device")
removable=$(lsblk -dn -o RM "$device")
[[ "$type" == disk ]] || {
  echo "error: target must be a whole disk" >&2
  exit 1
}
[[ "$removable" == 1 ]] || {
  echo "error: target is not reported removable; refusing" >&2
  exit 1
}
lsblk -dn -o PATH,MODEL,SIZE,TRAN,RM "$device" >&2
if grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo "warning: raw USB access is commonly unavailable or unsafe through WSL; prefer a Windows image writer" >&2
fi
printf 'Type the full device path to erase it: ' >&2
IFS= read -r confirmation
[[ "$confirmation" == "$device" ]] || {
  echo "error: confirmation mismatch" >&2
  exit 1
}
echo "Writing $iso to $device" >&2
dd if="$iso" of="$device" bs=4M status=progress conv=fsync
sync
echo "USB write completed" >&2
