#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} ISO RAW_DISK PID_FILE LOG_FILE

Internal E2E helper. Start a detached Q35/OVMF VM with a disposable raw virtio disk,
SSH forwarded to port 2222, and application HTTP forwarded to port 18080.
E2E_BOOT_ONCE=d boots rescue once (default); c boots only the installed disk.
EOF
}
[[ ${1:-} != -h && ${1:-} != --help ]] || {
  usage
  exit 0
}
[[ $# -eq 4 ]] || {
  usage >&2
  exit 2
}
iso=$1
disk=$2
pid_file=$3
log_file=$4
accel=tcg
cpu=max
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
  accel=kvm
  cpu=host
fi
firmware_dir=${E2E_OVMF_FD_DIR:-}
firmware_code="$firmware_dir/OVMF_CODE.fd"
firmware_vars_template="$firmware_dir/OVMF_VARS.fd"
[[ -r "$firmware_code" && -r "$firmware_vars_template" ]] || {
  echo "error: E2E_OVMF_FD_DIR must contain readable OVMF firmware; run through nix develop" >&2
  exit 1
}
# A writable per-VM variables image is required for the installer-created UEFI
# boot entry to survive the reboot. The immutable code image remains read-only.
firmware_vars="${pid_file}.vars.fd"
cp --reflink=auto "$firmware_vars_template" "$firmware_vars"
# Nix store firmware is read-only. QEMU must update this private per-VM copy,
# including when CI runs as an unprivileged user rather than root.
chmod 0600 "$firmware_vars"
boot_once=${E2E_BOOT_ONCE:-d}
[[ "$boot_once" == c || "$boot_once" == d ]] || {
  echo "error: E2E_BOOT_ONCE must be c (disk) or d (rescue ISO)" >&2
  exit 1
}
cdrom_args=()
if [[ "$boot_once" == d ]]; then
  cdrom_args=(-cdrom "$iso")
fi
qemu-system-x86_64 \
  -machine q35 -accel "$accel" -cpu "$cpu" -m 3072 -smp 2 \
  -drive "if=pflash,format=raw,unit=0,readonly=on,file=$firmware_code" \
  -drive "if=pflash,format=raw,unit=1,file=$firmware_vars" \
  -boot "order=c,once=$boot_once,menu=off" "${cdrom_args[@]}" \
  -drive "file=$disk,if=none,id=target-disk,format=raw" \
  -device "virtio-blk-pci,drive=target-disk,serial=nixos-e2e" \
  -nic user,model=virtio-net-pci,hostfwd=tcp::2222-:22,hostfwd=tcp::18080-:8080 \
  -display none -serial "file:$log_file" -monitor none \
  -daemonize -pidfile "$pid_file"
