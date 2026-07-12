#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=${PROJECT_ROOT:-$(cd -- "$SCRIPT_DIR/.." && pwd)}
# shellcheck source=provisioning/lib/common.sh
source "$ROOT/provisioning/lib/common.sh"
# shellcheck source=provisioning/lib/remote.sh
source "$ROOT/provisioning/lib/remote.sh"

usage() {
  cat <<EOF
Usage: ${0##*/} --target root@HOST --host HOST --admin-key-file FILE [OPTIONS]

Discover a rescue host, select and confirm one safe disk, install NixOS with the
pinned nixos-anywhere/disko inputs, reboot, and verify the installed services.

Required:
  --target root@HOST          SSH target running the rescue environment
  --host NAME                Flake NixOS configuration (for example m710q)
  --admin-key-file FILE      Public key installed for the non-root admin user

Options:
  --disk BY_ID               Reviewed /dev/disk/by-id/... whole-disk path
  --identity FILE            Private SSH identity used from this development PC
  --port PORT                SSH port (default: 22)
  --application-env-file FILE
                              Root-only dotenv file copied to
                              /var/lib/mini-pc/secrets/compose.env
  --yes --ci-disposable      Bypass typing the disk path only for disposable CI
  -h, --help                 Show this help

Safety and secrets:
  Physical installs require typing the complete selected disk path. Secret values
  are copied as runtime files with nixos-anywhere --extra-files; they are never
  interpolated into the temporary Nix module. Create a suitable file with
  scripts/create-secrets-file.sh. Do not pass secret values on the command line.

Example:
  nix run .#install -- --target root@nixos-rescue.local --host m710q \\
    --admin-key-file ~/.ssh/id_ed25519.pub --identity ~/.ssh/id_ed25519 \\
    --application-env-file secrets/compose.env
EOF
}

target=""
host=""
disk=""
identity_file=""
admin_key_file=""
application_env_file=""
port=22
assume_yes=false
ci_disposable=false
while (($#)); do
  case "$1" in
    --target)
      target=${2:?missing target}
      shift 2
      ;;
    --host)
      host=${2:?missing host}
      shift 2
      ;;
    --disk)
      disk=${2:?missing disk}
      shift 2
      ;;
    --identity)
      identity_file=${2:?missing identity}
      shift 2
      ;;
    --admin-key-file)
      admin_key_file=${2:?missing public key file}
      shift 2
      ;;
    --application-env-file)
      application_env_file=${2:?missing application environment file}
      shift 2
      ;;
    --port)
      port=${2:?missing port}
      shift 2
      ;;
    --yes)
      assume_yes=true
      shift
      ;;
    --ci-disposable)
      ci_disposable=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ -n "$target" && -n "$host" ]] || {
  usage >&2
  exit 2
}
[[ "$target" == root@* ]] || die "rescue target must explicitly use root@HOST"
[[ "$host" =~ ^[a-zA-Z0-9-]+$ ]] || die "invalid host configuration name"
[[ -r "$admin_key_file" ]] || die "--admin-key-file must name a readable public key"
grep -Eq '^ssh-(ed25519|rsa|ecdsa-[^ ]+) [A-Za-z0-9+/=]+' "$admin_key_file" || die "admin key file does not contain an OpenSSH public key"
if [[ -n "$application_env_file" ]]; then
  [[ -f "$application_env_file" && -r "$application_env_file" ]] ||
    die "application environment file is not a readable regular file: $application_env_file"
  mode=$(stat -c '%a' "$application_env_file")
  (((8#$mode & 077) == 0)) ||
    die "application environment file must not be readable or writable by group/others (use chmod 600)"
  grep -Ev '^(#|[[:space:]]*$|[A-Za-z_][A-Za-z0-9_]*=.*)$' "$application_env_file" | grep -q . &&
    die "application environment file must contain only NAME=value lines, comments, or blanks"
fi
if $assume_yes && ! $ci_disposable; then
  die "--yes is accepted only together with --ci-disposable"
fi
require_command jq
require_command nix
require_command ssh

project=$(project_root)
[[ -e "$project/flake.nix" ]] || die "project flake is unavailable: $project"
run_ssh "$target" "$port" "$identity_file" true >/dev/null || die "cannot connect to rescue SSH at $target:$port"

tmpdir=$(mktemp -d)
trap 'cleanup_dir "$tmpdir"' EXIT
report="$tmpdir/discovery.json"
discover_args=(--output "$report" --port "$port")
[[ -z "$identity_file" ]] || discover_args+=(--identity "$identity_file")
"$ROOT/provisioning/discover-hardware.sh" "${discover_args[@]}" "$target" >/dev/null

selector_args=()
[[ -z "$disk" ]] || selector_args+=(--disk "$disk")
disk=$("$ROOT/provisioning/select-disk.sh" "${selector_args[@]}" "$report")
model=$(jq -r --arg disk "$disk" '.by_id[] | select(.path==$disk) | .target as $target | $target' "$report" | head -1)
disk_info=$(jq -r --arg path "$model" '.block_devices.blockdevices[] | select(.path==$path) | "\(.model // "unknown") | \(.size) bytes | serial \(.serial // "unknown")"' "$report")
log "DESTRUCTIVE INSTALLATION SUMMARY"
log "  Rescue target: $target"
log "  NixOS configuration: $host"
log "  Whole disk to erase: $disk"
log "  Device: $disk_info"
log "  Discovery report: $report (temporary)"

if ! $assume_yes; then
  printf 'Type the full disk path to continue: ' >&2
  IFS= read -r confirmation
  [[ "$confirmation" == "$disk" ]] || die "confirmation did not exactly match the selected disk"
else
  log "CI disposable-disk confirmation bypass is active"
fi

admin_key=$(head -1 "$admin_key_file")
disk_nix=$(jq -Rn --arg value "$disk" '$value')
key_nix=$(jq -Rn --arg value "$admin_key" '$value')
base_url=$(jq -Rn --arg value "path:$project" '$value')
cat_template=$(printf '%s\n' \
  '{' \
  "  inputs.base.url = $base_url;" \
  '  outputs = { base, ... }: {' \
  "    nixosConfigurations.\"$host\" = base.nixosConfigurations.\"$host\".extendModules {" \
  '      modules = [ ./runtime.nix ];' \
  '    };' \
  '  };' \
  '}')
runtime_template=$(printf '%s\n' '{' "  my.install.targetDisk = $disk_nix;" "  my.ssh.authorizedKeys = [ $key_nix ];" '}')
printf '%s\n' "$cat_template" >"$tmpdir/flake.nix"
printf '%s\n' "$runtime_template" >"$tmpdir/runtime.nix"

# --extra-files copies this tree directly to the target filesystem. Keeping the
# dotenv file out of runtime.nix prevents its values from becoming world-readable
# Nix store objects. The temporary directory is removed by the EXIT trap.
if [[ -n "$application_env_file" ]]; then
  secret_dir="$tmpdir/extra-files/var/lib/mini-pc/secrets"
  install -d -m 0700 "$secret_dir"
  install -m 0600 "$application_env_file" "$secret_dir/compose.env"
fi

log "Starting pinned nixos-anywhere; this is the first destructive operation"
anywhere_args=(
  --flake "$tmpdir#$host"
  --target-host "$target"
  --ssh-port "$port"
  --copy-host-keys
)
[[ -z "$identity_file" ]] || anywhere_args+=(-i "$identity_file")
if [[ -n "${SSH_USER_KNOWN_HOSTS_FILE:-}" ]]; then
  anywhere_args+=(--ssh-option "UserKnownHostsFile=$SSH_USER_KNOWN_HOSTS_FILE")
fi
if [[ -n "$application_env_file" ]]; then
  anywhere_args+=(
    --extra-files "$tmpdir/extra-files"
    --chown /var/lib/mini-pc/secrets 0:0
  )
fi
nix run "path:$project#nixos-anywhere" -- "${anywhere_args[@]}"

installed_host="admin@${target#*@}"
verify_args=(--target "$installed_host" --port "$port" --timeout 600)
[[ -z "$identity_file" ]] || verify_args+=(--identity "$identity_file")
"$ROOT/provisioning/verify-installed.sh" "${verify_args[@]}"
