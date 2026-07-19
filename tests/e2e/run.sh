#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  cat <<EOF
Usage: ${0##*/}

Run the full disposable provisioning E2E: build a key-injected rescue ISO, prove a
fresh 12 GiB raw disk is unchanged by rescue boot, discover/select it, install through
nixos-anywhere/disko, reboot, rotate secrets, exercise a no-op deployment, and verify
SSH plus LAN HTTPS health.

Run through: nix develop -c timeout 100m tests/e2e/run.sh
Only .e2e/target.raw may be erased. KVM is preferred; TCG can be very slow.
EOF
  exit 0
fi
[[ $# -eq 0 ]] || {
  echo "error: ${0##*/} accepts no arguments (try --help)" >&2
  exit 2
}

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
WORK="$ROOT/.e2e"
rm -rf -- "$WORK"
mkdir -p "$WORK"
trap '"$ROOT/tests/e2e/collect-logs.sh" "$WORK"' EXIT

# The ephemeral key exists only in the ignored E2E workspace and is never committed.
ssh-keygen -q -t ed25519 -N '' -f "$WORK/id_ed25519" -C nixos-e2e
export SSH_USER_KNOWN_HOSTS_FILE="$WORK/known_hosts"
: >"$SSH_USER_KNOWN_HOSTS_FILE"
public_key=$(<"$WORK/id_ed25519.pub")
key_nix=$(jq -Rn --arg value "$public_key" '$value')
base_url=$(jq -Rn --arg value "path:$ROOT" '$value')
printf '%s\n' \
  '{' \
  "  inputs.base.url = $base_url;" \
  '  outputs = { base, ... }: {' \
  '    packages.x86_64-linux.iso = (base.nixosConfigurations.rescue-iso.extendModules {' \
  '      modules = [ ./key.nix ];' \
  '    }).config.system.build.isoImage;' \
  '  };' \
  '}' >"$WORK/flake.nix"
printf '%s\n' '{' "  my.rescue.authorizedKeys = [ $key_nix ];" '}' >"$WORK/key.nix"
printf '%s\n' \
  'ACTUAL_PASSWORD=disposable-test-value' \
  'ACTUAL_FILE=disposable-test-budget' \
  'DISCORD_TOKEN=disposable-test-token' \
  'DISCORD_BANK_NOTIFICATION_CHANNEL=disposable-test-channel' >"$WORK/compose.env"
chmod 0600 "$WORK/compose.env"

nix build "path:$WORK#iso" -o "$WORK/iso-result" --print-build-logs
iso=$(find -L "$WORK/iso-result/iso" -maxdepth 1 -type f -name '*.iso' -print -quit)
[[ -n "$iso" ]] || {
  echo "error: rescue ISO output is missing" >&2
  exit 1
}
truncate -s 12G "$WORK/target.raw"
before=$(sha256sum "$WORK/target.raw" | cut -d' ' -f1)

"$ROOT/tests/e2e/start-rescue-vm.sh" "$iso" "$WORK/target.raw" "$WORK/pid" "$WORK/qemu.log"
"$ROOT/tests/e2e/wait-for-ssh.sh" root@127.0.0.1 2222 "$WORK/id_ed25519" 300
nix run "path:$ROOT#discover" -- \
  --identity "$WORK/id_ed25519" --port 2222 --output "$WORK/discovery.json" root@127.0.0.1
nix run "path:$ROOT#select-disk" -- "$WORK/discovery.json" | grep -qx '/dev/disk/by-id/virtio-nixos-e2e'
qemu_pid=$(<"$WORK/pid")
kill "$qemu_pid"
while kill -0 "$qemu_pid" 2>/dev/null; do sleep 1; done
# This hash is the central non-destructive rescue assertion. Installation begins
# only in the second VM boot below.
after=$(sha256sum "$WORK/target.raw" | cut -d' ' -f1)
[[ "$before" == "$after" ]] || {
  echo "error: rescue-only boot modified the target disk" >&2
  exit 1
}
: >"$SSH_USER_KNOWN_HOSTS_FILE"

"$ROOT/tests/e2e/start-rescue-vm.sh" "$iso" "$WORK/target.raw" "$WORK/pid" "$WORK/qemu.log"
"$ROOT/tests/e2e/wait-for-ssh.sh" root@127.0.0.1 2222 "$WORK/id_ed25519" 300
CI=true nix run "path:$ROOT#install" -- \
  --target root@127.0.0.1 --port 2222 --host e2e-target \
  --installed-target admin@127.0.0.1 \
  --disk /dev/disk/by-id/virtio-nixos-e2e \
  --identity "$WORK/id_ed25519" --admin-key-file "$WORK/id_ed25519.pub" \
  --application-env-file "$WORK/compose.env" \
  --yes --ci-disposable
ssh -i "$WORK/id_ed25519" -p 2222 \
  -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  admin@127.0.0.1 \
  "sudo sh -c 'test \"\$(stat -c %a /var/lib/mini-pc/secrets/discord-bot.env)\" = 600 && grep -q \"^DISCORD_TOKEN=\" /var/lib/mini-pc/secrets/discord-bot.env'"

printf '%s\n' \
  'ACTUAL_PASSWORD=rotated-disposable-test-value' \
  'ACTUAL_FILE=rotated-disposable-test-budget' \
  'DISCORD_TOKEN=rotated-disposable-test-token' \
  'DISCORD_BANK_NOTIFICATION_CHANNEL=rotated-disposable-test-channel' >"$WORK/rotated.env"
chmod 0600 "$WORK/rotated.env"
CI=true nix run "path:$ROOT#deploy" -- \
  --target admin@127.0.0.1 --port 2222 \
  --identity "$WORK/id_ed25519" --secrets-only \
  --application-env-file "$WORK/rotated.env" \
  --yes --ci-disposable
ssh -i "$WORK/id_ed25519" -p 2222 \
  -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  admin@127.0.0.1 \
  "sudo grep -qx 'DISCORD_TOKEN=rotated-disposable-test-token' /var/lib/mini-pc/secrets/discord-bot.env"

CI=true nix run "path:$ROOT#deploy" -- \
  --target admin@127.0.0.1 --port 2222 --host e2e-target \
  --identity "$WORK/id_ed25519" --admin-key-file "$WORK/id_ed25519.pub" \
  --application-env-file "$WORK/rotated.env" \
  --yes --ci-disposable
ssh -i "$WORK/id_ed25519" -p 2222 \
  -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  admin@127.0.0.1 true
curl --fail --insecure --silent --show-error --max-time 10 \
  --resolve actual.e2e.test:18443:127.0.0.1 \
  https://actual.e2e.test:18443/health >/dev/null
echo "full provisioning, secret rotation, and no-op deployment E2E passed"
