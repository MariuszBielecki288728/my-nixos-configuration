#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} TARGET PORT IDENTITY TIMEOUT

Internal E2E readiness probe. Poll SSH with an isolated, disposable host-key policy
until success or TIMEOUT seconds. Production provisioning uses accept-new instead.
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
target=$1
port=$2
identity=$3
timeout=$4
deadline=$((SECONDS + timeout))
while ((SECONDS < deadline)); do
  if ssh -i "$identity" -p "$port" \
    -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=3 "$target" true >/dev/null 2>&1; then
    exit 0
  fi
  sleep 2
done
echo "error: SSH did not become ready in ${timeout}s" >&2
exit 1
