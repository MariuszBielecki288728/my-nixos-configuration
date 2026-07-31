# Testing and continuous integration

## Local validation

Run small checks before expensive virtual-machine tests:

```bash
nix develop
just fmt
just lint
just test-python
just check-fast
```

Then build the complete flake checks and rescue artifacts:

```bash
nix flake check --print-build-logs
nix build .#rescue-iso .#pxe-bundle --print-build-logs
```

NixOS VM tests can require substantial Nix-store space. KVM is preferred. WSL2 often
lacks usable KVM, so QEMU TCG tests may be slow; the same tests remain mandatory in CI.

## Coverage by feature

| Feature | Automated evidence |
| --- | --- |
| Python policy and CLI | pytest covers parsing, key handling, discovery models, disk selection, networking policy, sessions, orchestration, secret validation, deployment confirmation, health gates, and rollback |
| Formatting and static analysis | nixfmt, Ruff, Black, ShellCheck, actionlint, and Compose validation |
| Generic and M710q configurations | NixOS toplevel closure builds |
| Disk layout | `tests/disk-layout.nix` partitions and mounts a disposable VM disk |
| SSH and application services | `tests/services.nix` verifies key-only SSH, Docker, pinned images, Actual health, proxy headers, persistence, backup, and restore |
| Monitoring | the service VM verifies Netdata health/history, dedicated user, analytics opt-out, disabled privileged/Docker collectors, loopback-only backend, HTTPS 8443, legacy redirects, and CIDR firewall policy |
| Rescue safety | `tests/rescue.nix` verifies DHCP, SSH, diagnostics, absence of an installer unit, and unchanged disposable-disk content |
| PXE delivery | `tests/pxe/run.sh` boots OVMF through DHCP/TFTP/iPXE/HTTP, reaches rescue SSH and discovery, and hashes the disposable disk before and after |
| End-to-end installation | `tests/e2e/run.sh` boots the shared rescue ISO, discovers/selects a disposable disk, installs with nixos-anywhere, reboots, and verifies SSH and services |
| Repository boundaries | `tests/repository.sh` proves generated, session, VM, and secret paths are ignored and rejects a return to parallel plan/investigation documents |

Physical sensor availability, firmware boot fallback, browser service-worker behavior,
Discord interactions, and real client CA installation require physical acceptance.
Their observed results belong in the relevant operations guide, not in test fixtures.

## GitHub Actions

`check.yaml` runs Python checks, formatting, repository-boundary checks, flake
evaluation/builds, rescue artifact builds, and the PXE integration test. The
`provisioning-e2e.yaml` workflow runs the destructive path only against its disposable
virtual disk. Both integration workflows use timeouts and retain logs as artifacts.

`release-iso.yaml` builds a key-authorized rescue ISO for manual runs or version tags.
Tag pushes create a draft release with the ISO and checksum. The required
`RESCUE_SSH_PUBLIC_KEY` repository variable is public-key material, not a secret.

Third-party actions are pinned to full commits and workflow permissions are minimal.
Production application credentials are not available to CI.

## Interpreting failures

A local out-of-space or unavailable-KVM error is an environment failure only when the
test did not boot or execute assertions. Record it explicitly and rely on CI only
after the same revision passes formatting, evaluation, and the relevant closure build.
Test assertion failures, health failures, and disk-safety failures must be fixed; they
must never be bypassed by weakening confirmation or validation.
