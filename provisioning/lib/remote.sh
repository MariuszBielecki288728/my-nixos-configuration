#!/usr/bin/env bash
set -Eeuo pipefail

ssh_options() {
  local connect_timeout="${SSH_CONNECT_TIMEOUT:-10}"
  local -a options=(
    -o "BatchMode=yes"
    -o "ConnectTimeout=$connect_timeout"
    -o "ServerAliveInterval=5"
    -o "ServerAliveCountMax=3"
    -o "StrictHostKeyChecking=accept-new"
  )
  if [[ -n "${SSH_USER_KNOWN_HOSTS_FILE:-}" ]]; then
    options+=(-o "UserKnownHostsFile=$SSH_USER_KNOWN_HOSTS_FILE")
  fi
  printf '%s\0' "${options[@]}"
}

run_ssh() {
  local target="$1"
  local port="$2"
  local identity_file="$3"
  shift 3
  local -a options
  mapfile -d '' -t options < <(ssh_options)
  [[ -z "$identity_file" ]] || options+=(-i "$identity_file" -o IdentitiesOnly=yes)
  ssh "${options[@]}" -p "$port" "$target" "$@"
}

wait_for_ssh() {
  local target="$1"
  local port="$2"
  local identity_file="$3"
  local timeout="$4"
  local deadline=$((SECONDS + timeout))
  while ((SECONDS < deadline)); do
    if run_ssh "$target" "$port" "$identity_file" true >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}
