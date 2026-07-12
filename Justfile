set shell := ["bash", "-Eeuo", "pipefail", "-c"]

fmt:
  nix fmt
  shfmt -w -i 2 -ci provisioning scripts tests/*.sh tests/e2e pxe/build-pxe.sh

lint:
  shellcheck provisioning/*.sh provisioning/lib/*.sh scripts/*.sh tests/*.sh tests/e2e/*.sh pxe/build-pxe.sh

check:
  nix flake check --print-build-logs

check-fast:
  nix flake check --no-build
  bash tests/selector.sh
  bash tests/secrets.sh
  bash tests/repository.sh
  just lint

build-iso:
  nix build .#rescue-iso --print-build-logs

run-rescue-vm:
  scripts/run-rescue-vm.sh

e2e:
  tests/e2e/run.sh
