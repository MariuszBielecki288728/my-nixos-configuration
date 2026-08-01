# Generic NixOS mini-PC provisioning

This repository is a reproducible, safety-conscious NixOS provisioning and operations
system for x86_64 UEFI mini PCs. The Lenovo ThinkCentre M710q (10MQ) is the first
production target, while the rescue system, disk policy, host modules, and deployment
tools remain reusable.

The current M710q services are:

| Service | Address | Access |
| --- | --- | --- |
| Actual Budget | `https://think-centre.home/` | reviewed LAN CIDR through Caddy |
| Device status | `https://think-centre.home:8443/` | reviewed LAN CIDR through Caddy |
| SSH | `admin@think-centre.home` | key-only administration |

The status page uses a separate HTTPS origin because Actual installs a root-scoped
service worker. In browsers that have opened Actual, `/status/` may be handled as an
Actual route and open `/budget` before the request reaches Caddy.

> **Disk safety:** booting rescue never installs anything. Only an explicit remote
> installation can erase a disk. Selection fails unless exactly one safe disk remains
> or the operator supplies a validated `/dev/disk/by-id/...` path, and interactive use
> requires typing the complete selected path.

## How the system fits together

```text
USB ISO | PXE/iPXE | QEMU
          |
          v
shared rescue system (DHCP, SSH, diagnostics; never auto-installs)
          |
          v
read-only discovery -> fail-closed disk selection -> explicit confirmation
          |
          v
pinned nixos-anywhere + disko -> reboot -> installed-host verification
          |
          v
transactional NixOS/application updates with health-check rollback
```

See [architecture](docs/ARCHITECTURE.md) for the component contracts and design
decisions, and [the roadmap](docs/ROADMAP.md) for work intentionally left after MVP.

## Development setup

Keep a WSL2 checkout in the Linux filesystem rather than `/mnt/c`. Nix must have the
`nix-command` and `flakes` features enabled. Enter the pinned tool environment and run
the fast checks:

```bash
nix develop
just check-fast
```

The provisioning package targets Python 3.14. For an editable local environment:

```bash
python3 -m venv ./venv
./venv/bin/python -m pip install uv
./venv/bin/uv sync --project python --active
./venv/bin/pytest -c python/pyproject.toml
```

Private keys, tokens, passwords, discovery reports, and provisioning sessions are
never source files. Read [secrets](docs/SECRETS.md) and [repository layout](docs/REPOSITORY_LAYOUT.md)
before supplying production values.

## Provision a machine

The preferred physical workflow uses a dedicated Ethernet cable and temporary,
isolated PXE services:

```bash
sudo -E just -- provision-m710q \
  --interface REPLACE_WITH_DEDICATED_ETHERNET
```

The command creates or accepts SSH keys, boots the shared rescue environment, records
read-only discovery, selects a disk only when safe, asks for the full stable path,
installs, switches PXE off before reboot, verifies the installed system, and cleans up
temporary network services. Each attempt leaves a private ignored evidence directory
under `artifacts/sessions/`.

USB rescue and lower-level discovery/install commands are also supported. Follow the
[provisioning guide](docs/PROVISIONING.md); do not improvise a disk path or start the
temporary DHCP service on an existing LAN.

## Update the installed host

Full updates are built on the development PC and activated only after an explicit
target confirmation:

```bash
nix run .#deploy -- \
  --target admin@think-centre.home \
  --host m710q \
  --identity ~/.ssh/mini_pc_provision_ed25519 \
  --admin-key-file ~/.ssh/mini_pc_provision_ed25519.pub
```

The deployment preserves the admin key, copies immutable images with the system
closure, takes a pre-activation Actual backup, activates the candidate, and runs both
application and monitoring health checks. Failure restores the previous generation
and any replaced secret file. It never prunes generations automatically.

For routine operations, secret rotation, update policy, rollback, and diagnostics,
use [application operations](docs/APPLICATION_OPERATIONS.md). Status-page usage and
sensor details are in [monitoring operations](docs/MONITORING.md).

## Validate changes

```bash
just fmt
just lint
just test-python
just check-fast
nix flake check --print-build-logs
nix build .#rescue-iso .#pxe-bundle --print-build-logs
just pxe-test
```

The full disposable provisioning test is:

```bash
nix develop -c timeout 100m tests/e2e/run.sh
```

KVM is used when available; QEMU TCG is a much slower fallback. See [testing and CI](docs/TESTING.md)
for the feature matrix, local constraints, and workflow behavior.

## Documentation

- [Architecture](docs/ARCHITECTURE.md): system boundaries and accepted decisions.
- [Provisioning](docs/PROVISIONING.md): PXE, USB, discovery, installation, and troubleshooting.
- [Application operations](docs/APPLICATION_OPERATIONS.md): deployment, updates, rollback, and incidents.
- [Monitoring](docs/MONITORING.md): status dashboard, sensors, retention, and troubleshooting.
- [Backup and restore](docs/BACKUP_AND_RESTORE.md): protected Actual data operations.
- [Secrets](docs/SECRETS.md): threat model, bootstrap, and rotation.
- [Command reference](docs/SCRIPTS.md): operator commands and safety classification.
- [Testing and CI](docs/TESTING.md): automated coverage and release workflows.
- [Repository layout](docs/REPOSITORY_LAYOUT.md): source, generated, private, and secret paths.
- [Roadmap](docs/ROADMAP.md): unapplied improvements after MVP.
