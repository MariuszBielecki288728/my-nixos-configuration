#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} [ISO]

Boot rescue interactively in QEMU with user networking, SSH forwarded to localhost
port 2222, and a newly created disposable 8 GiB qcow2 disk. The disk is deleted when
QEMU exits. KVM is used when writable; otherwise the command falls back to TCG.

This helper does not test installation. Use tests/e2e/run.sh for full provisioning.
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
default_iso=$(find -L result/iso -maxdepth 1 -type f -name '*.iso' -print -quit 2>/dev/null || true)
iso=${1:-$default_iso}
[[ -f "$iso" ]] || {
  echo "error: build the ISO first with nix build .#rescue-iso" >&2
  exit 1
}
disk=$(mktemp --suffix=.qcow2)
trap 'rm -f -- "$disk"' EXIT
qemu-img create -q -f qcow2 "$disk" 8G
accel=tcg
cpu=max
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
  accel=kvm
  cpu=host
fi
exec qemu-system-x86_64 \
  -accel "$accel" -m 2048 -cpu "$cpu" \
  -boot once=d -cdrom "$iso" \
  -drive "file=$disk,if=none,id=rescue-demo-disk,format=qcow2" \
  -device "virtio-blk-pci,drive=rescue-demo-disk,serial=rescue-demo" \
  -nic user,model=virtio-net-pci,hostfwd=tcp::2222-:22 \
  -nographic
