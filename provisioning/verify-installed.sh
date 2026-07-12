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
Usage: ${0##*/} --target admin@HOST [OPTIONS]

Wait for an installed host, then require active sshd, Docker, the Compose systemd
unit, and a successful HTTP response from 127.0.0.1:8080.

Options:
  --target USER@HOST  Installed-system SSH target (required)
  --port PORT         SSH port (default: 22)
  --identity FILE     Local private SSH identity
  --timeout SECONDS   Timeout for SSH and service readiness (default: 300)
  -h, --help          Show this help

On a service timeout, unit status and the final HTTP error are printed for diagnosis.
EOF
}

target=""
port=22
identity_file=""
timeout=300
while (($#)); do
  case "$1" in
    --target)
      target=${2:?missing target}
      shift 2
      ;;
    --port)
      port=${2:?missing port}
      shift 2
      ;;
    --identity)
      identity_file=${2:?missing identity}
      shift 2
      ;;
    --timeout)
      timeout=${2:?missing timeout}
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ -n "$target" ]] || {
  usage >&2
  exit 2
}
log "Waiting up to ${timeout}s for installed-system SSH at $target:$port"
wait_for_ssh "$target" "$port" "$identity_file" "$timeout" || die "installed-system SSH did not become ready"
deadline=$((SECONDS + timeout))
while ((SECONDS < deadline)); do
  if run_ssh "$target" "$port" "$identity_file" \
    'systemctl is-active --quiet sshd docker mini-pc-application && curl --fail --silent --max-time 10 http://127.0.0.1:8080/ >/dev/null' 2>/dev/null; then
    log "Installed system, Docker Compose service, and HTTP health are ready"
    exit 0
  fi
  sleep 5
done
run_ssh "$target" "$port" "$identity_file" \
  'systemctl --no-pager --full status sshd docker mini-pc-application; curl --fail --show-error --max-time 10 http://127.0.0.1:8080/' || true
die "installed services did not become healthy within ${timeout}s"
