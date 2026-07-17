#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  cat <<EOF
Usage: ${0##*/}

Boot the shared rescue system through real UEFI PXE -> TFTP -> iPXE -> HTTP,
verify SSH and disk discovery, and prove rescue did not modify the disposable raw disk.
The test creates and removes one explicitly named TAP device with sudo.
EOF
  exit 0
fi
[[ $# -eq 0 ]] || {
  echo "error: ${0##*/} accepts no arguments" >&2
  exit 2
}

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
WORK="$ROOT/.e2e/pxe"
TAP="mpcp$$"
SERVER=192.168.77.1
CLIENT=192.168.77.2
qemu_pid=
dnsmasq_pid=
http_pid=

cleanup() {
  set +e
  if [[ -n $qemu_pid ]]; then
    kill "$qemu_pid" 2>/dev/null
    wait "$qemu_pid" 2>/dev/null
  fi
  [[ -n $http_pid ]] && kill "$http_pid" 2>/dev/null
  [[ -n $dnsmasq_pid ]] && sudo kill "$dnsmasq_pid" 2>/dev/null
  sudo ip link delete "$TAP" 2>/dev/null
  mkdir -p "$WORK/logs"
  cp -f "$WORK"/*.log "$WORK/logs/" 2>/dev/null
  cp -f "$WORK/discovery.json" "$WORK/logs/" 2>/dev/null
}
trap cleanup EXIT

rm -rf -- "$WORK"
mkdir -p "$WORK"
ssh-keygen -q -t ed25519 -N '' -f "$WORK/id_ed25519" -C nixos-pxe-e2e
public_key=$(<"$WORK/id_ed25519.pub")
key_nix=$(jq -Rn --arg value "$public_key" '$value')
base_url=$(jq -Rn --arg value "path:$ROOT" '$value')
printf '%s\n' \
  '{' \
  "  inputs.base.url = $base_url;" \
  '  outputs = { base, ... }: {' \
  '    packages.x86_64-linux.default = base.lib.x86_64-linux.mkPxeBundle' \
  '      (base.nixosConfigurations.rescue-pxe.extendModules {' \
  '        modules = [ ./key.nix ];' \
  '      }).config;' \
  '  };' \
  '}' >"$WORK/flake.nix"
printf '%s\n' '{' "  my.rescue.authorizedKeys = [ $key_nix ];" '}' >"$WORK/key.nix"
nix build "path:$WORK" -o "$WORK/bundle" --print-build-logs
BUNDLE=$(readlink -f "$WORK/bundle")

truncate -s 1G "$WORK/target.raw"
before=$(sha256sum "$WORK/target.raw" | cut -d' ' -f1)
sudo ip tuntap add dev "$TAP" mode tap user "$(id -u)"
sudo ip address add "$SERVER/24" dev "$TAP"
sudo ip link set dev "$TAP" up

cat >"$WORK/dnsmasq.conf" <<EOF
port=0
interface=$TAP
bind-interfaces
log-dhcp
dhcp-range=$CLIENT,$CLIENT,255.255.255.0,1h
dhcp-option=3,$SERVER
dhcp-leasefile=
dhcp-match=set:efi64,option:client-arch,7
dhcp-match=set:efi64,option:client-arch,9
dhcp-boot=tag:efi64,ipxe.efi,,$SERVER
dhcp-userclass=set:ipxe,iPXE
dhcp-boot=tag:ipxe,http://$SERVER:8081/nixos/boot.ipxe
enable-tftp
tftp-root=$BUNDLE/tftp
EOF
# shellcheck disable=SC2024 # The unprivileged caller intentionally owns this log.
sudo dnsmasq --keep-in-foreground --conf-file="$WORK/dnsmasq.conf" \
  >"$WORK/dnsmasq.log" 2>&1 &
dnsmasq_pid=$!
python3 -m http.server 8081 --bind "$SERVER" --directory "$BUNDLE/http" \
  >"$WORK/http.log" 2>&1 &
http_pid=$!
sleep 1
kill -0 "$dnsmasq_pid" "$http_pid" || {
  echo "error: temporary PXE services failed to start" >&2
  exit 1
}

firmware_dir=${E2E_OVMF_FD_DIR:-}
[[ -r $firmware_dir/OVMF_CODE.fd && -r $firmware_dir/OVMF_VARS.fd ]] || {
  echo "error: E2E_OVMF_FD_DIR is missing; run through nix develop" >&2
  exit 1
}
cp "$firmware_dir/OVMF_VARS.fd" "$WORK/OVMF_VARS.fd"
chmod 0600 "$WORK/OVMF_VARS.fd"
accel=tcg
cpu=max
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
  accel=kvm
  cpu=host
fi
qemu-system-x86_64 \
  -machine q35 -accel "$accel" -cpu "$cpu" -m 4096 -smp 2 \
  -drive "if=pflash,format=raw,unit=0,readonly=on,file=$firmware_dir/OVMF_CODE.fd" \
  -drive "if=pflash,format=raw,unit=1,file=$WORK/OVMF_VARS.fd" \
  -boot order=n,menu=off \
  -drive "file=$WORK/target.raw,if=none,id=target-disk,format=raw" \
  -device "virtio-blk-pci,drive=target-disk,serial=pxe-e2e" \
  -netdev "tap,id=net0,ifname=$TAP,script=no,downscript=no" \
  -device e1000,netdev=net0 \
  -display none -serial "file:$WORK/qemu.log" -monitor none &
qemu_pid=$!

"$ROOT/tests/e2e/wait-for-ssh.sh" "root@$CLIENT" 22 "$WORK/id_ed25519" 600
nix run "path:$ROOT#discover" -- \
  --identity "$WORK/id_ed25519" --output "$WORK/discovery.json" "root@$CLIENT"
nix run "path:$ROOT#select-disk" -- "$WORK/discovery.json" |
  grep -qx '/dev/disk/by-id/virtio-pxe-e2e'

kill "$qemu_pid"
wait "$qemu_pid" || true
qemu_pid=
after=$(sha256sum "$WORK/target.raw" | cut -d' ' -f1)
[[ $before == "$after" ]] || {
  echo "error: PXE rescue modified the disposable target disk" >&2
  exit 1
}
echo "UEFI PXE/TFTP/iPXE/HTTP rescue integration passed"
