#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<EOF
Usage: ${0##*/} [--output FILE] [--name VARIABLE ...] [--force]

Create a root-only Docker Compose dotenv file without placing secret values in
shell history or process arguments. Values are read silently and confirmed.

Options:
  --output FILE       Destination (default: secrets/compose.env)
  --name VARIABLE     Secret variable to prompt for; repeat as needed
  --force             Replace an existing destination
  -h, --help          Show this help

If no --name is supplied, variable names are requested interactively until an
empty name is entered. Names must match [A-Za-z_][A-Za-z0-9_]*. Values must be
non-empty, single-line strings. The resulting file is created atomically as mode
0600 and is ignored by Git.

Example:
  scripts/create-secrets-file.sh --name DATABASE_PASSWORD --name API_TOKEN
  nix run .#install -- ... --application-env-file secrets/compose.env
EOF
}

output=secrets/compose.env
force=false
names=()
while (($#)); do
  case "$1" in
    --output)
      output=${2:?missing output file}
      shift 2
      ;;
    --name)
      names+=("${2:?missing variable name}")
      shift 2
      ;;
    --force)
      force=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if ((${#names[@]} == 0)); then
  while true; do
    read -rp 'Secret variable name (empty to finish): ' name
    [[ -n "$name" ]] || break
    names+=("$name")
  done
fi
((${#names[@]} > 0)) || {
  echo "error: at least one secret variable is required" >&2
  exit 1
}

for name in "${names[@]}"; do
  [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    echo "error: invalid environment variable name: $name" >&2
    exit 1
  }
done
[[ ! -e "$output" || "$force" == true ]] || {
  echo "error: refusing to replace existing file without --force: $output" >&2
  exit 1
}

umask 077
mkdir -p "$(dirname -- "$output")"
tmp=$(mktemp "${output}.tmp.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
printf '# Created by %s; do not commit this file.\n' "${0##*/}" >"$tmp"
for name in "${names[@]}"; do
  read -rsp "Value for $name: " value
  printf '\n' >&2
  read -rsp "Confirm $name: " confirmation
  printf '\n' >&2
  [[ -n "$value" ]] || {
    echo "error: $name must not be empty" >&2
    exit 1
  }
  [[ "$value" == "$confirmation" ]] || {
    echo "error: values for $name do not match" >&2
    exit 1
  }
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || {
    echo "error: $name must be a single-line value" >&2
    exit 1
  }
  # Compose treats single-quoted dotenv values literally, including '$'. Escape
  # the only character that terminates that representation.
  escaped=${value//\'/\\\'}
  printf "%s='%s'\n" "$name" "$escaped" >>"$tmp"
  unset value confirmation escaped
done
chmod 0600 "$tmp"
mv -f -- "$tmp" "$output"
trap - EXIT
printf 'Created %s with mode 0600. Pass it with --application-env-file.\n' "$output"
