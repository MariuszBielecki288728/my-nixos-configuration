set shell := ["bash", "-Eeuo", "pipefail", "-c"]

fmt:
  nix fmt
  uv run --project python ruff check --fix python
  uv run --project python black python
  shfmt -w -i 2 -ci scripts tests/*.sh tests/e2e pxe/build-pxe.sh

lint:
  uv run --project python ruff check python
  uv run --project python black --check python
  shellcheck scripts/*.sh tests/*.sh tests/e2e/*.sh pxe/build-pxe.sh

test-python:
  uv run --project python pytest -c python/pyproject.toml

check:
  nix flake check --print-build-logs

check-fast:
  nix flake check --no-build
  just test-python
  bash tests/secrets.sh
  bash tests/repository.sh
  just lint

build-iso:
  nix build .#rescue-iso --print-build-logs

run-rescue-vm:
  scripts/run-rescue-vm.sh

e2e:
  tests/e2e/run.sh
