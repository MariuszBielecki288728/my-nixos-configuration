#!/usr/bin/env bash
set -Eeuo pipefail

# This is intentionally a literal jq program, not a shell-expanded string.
# shellcheck disable=SC2016
disk_filter='def mounted: [.. | objects | select(has("mountpoints")) | (.mountpoints // [])[] | select(. != null)] | length > 0;
  def supported_transport($stable): (.tran == "sata" or .tran == "nvme" or .tran == "sas" or .tran == "scsi" or .tran == "virtio" or ((.tran == null or .tran == "") and ($stable | contains("/virtio-"))));
  [. as $root | $root.block_devices.blockdevices[]
    | select(.type == "disk")
    | select(.rm == false or .rm == 0 or .rm == "0")
    | select(.tran != "usb")
    | select(mounted | not)
    | . as $disk
    | ([$root.by_id[] | select(.target == $disk.path) | .path] | sort | .[0]) as $stable
    | select($stable != null)
    | select(supported_transport($stable))
    | $disk + {stable_path: $stable}
  ]'

safe_candidates() {
  local report="$1"
  jq -c "$disk_filter" "$report"
}
