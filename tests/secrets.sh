#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  echo "Usage: ${0##*/}  # test the interactive secret-file helper in a temporary directory"
  exit 0
fi
[[ $# -eq 0 ]] || exit 2

ROOT=${PROJECT_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
output="$work/compose.env"

# shellcheck disable=SC2016 # Literal '$' verifies Compose-safe secret quoting.
printf '%s\n' 'value$with#symbols' 'value$with#symbols' |
  bash "$ROOT/scripts/create-secrets-file.sh" --output "$output" --name API_TOKEN >/dev/null
[[ $(stat -c '%a' "$output") == 600 ]]
grep -Fqx "API_TOKEN='value\$with#symbols'" "$output"

if printf '%s\n' one two |
  bash "$ROOT/scripts/create-secrets-file.sh" --output "$work/mismatch.env" --name PASSWORD >/dev/null 2>&1; then
  echo "mismatched secret confirmation unexpectedly succeeded" >&2
  exit 1
fi
[[ ! -e "$work/mismatch.env" ]]
echo "secret helper tests passed"
