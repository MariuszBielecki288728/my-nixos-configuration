# AGENTS.md

## Mission

Build and maintain a generic, reproducible and safety-conscious NixOS provisioning system for x86_64 mini PCs.

The repository must provide:

- a reusable NixOS server configuration;
- a generic non-destructive rescue ISO;
- SSH access to the rescue environment;
- remote hardware discovery;
- safe disk selection;
- remote installation through `nixos-anywhere` and `disko`;
- Docker Compose application deployment;
- automated VM and end-to-end tests;
- GitHub Actions workflows.

The Lenovo ThinkCentre M710q is the first target, but the design must remain reusable for other compatible mini PCs.

All source code, comments, documentation and commit messages must be in English.

## Read First

Before changing anything:

1. Read `IMPLEMENTATION_PLAN.md`.
2. Read `README.md`.
3. Inspect `flake.nix`, `flake.lock` and Git status.
4. Determine whether the shell is WSL2.
5. Check whether systemd and Nix are already available.
6. Do not invent machine-specific disk IDs, DMI values, interface names or SSH keys.

## Architecture Rules

The preferred workflow is:

```text
generic rescue environment delivered by USB, PXE/iPXE, or QEMU
    -> DHCP and SSH
    -> remote discovery from development PC
    -> safe disk selection
    -> nixos-anywhere and disko
    -> reboot
    -> verify installed system
```

The rescue environment must never erase disks automatically after boot.

Provisioning logic must be independent of whether rescue was delivered by USB, PXE/iPXE or QEMU.

Do not reintroduce an autonomous boot-time installer unless the user explicitly changes the architecture.

Machine-specific data should be minimized.

Prefer:

- generic x86_64 hardware modules;
- Ethernet matching by device type;
- DHCP;
- runtime disk selection;
- host-specific overrides only when required.


## Rescue Delivery Independence

Define one shared rescue system and keep delivery-specific wrappers thin.

Supported delivery targets:

- USB ISO;
- PXE/iPXE;
- QEMU tests.

Rules:

- discovery starts only after SSH connectivity exists;
- installation starts only after explicit remote invocation;
- discovery and disk-selection code must not assume USB boot;
- USB/PXE/QEMU must converge on the same rescue behavior;
- booting any rescue output must be non-destructive;
- PXE server examples must not rewrite router or host DHCP configuration automatically.

PXE is allowed to be a later milestone, but current abstractions must not make it difficult to add.

## Known First Target

The first physical target is:

```text
Lenovo ThinkCentre M710q / M710 Tiny
Machine type 10MQ
Intel Pentium G4400T
x86_64
```

Do not design around Intel AMT, vPro remote KVM, remote BIOS control or remote ISO redirection for this target.

Wake-on-LAN may be supported after one-time firmware and operating-system configuration, but it does not solve boot-device selection.

Assume one local BIOS/UEFI setup session may be necessary for USB/PXE enablement and boot priority.

## Safety Rules

This project can erase disks.

Never:

- run destructive disk commands against the development host;
- auto-install merely because the ISO booted;
- assume `/dev/sda` is the target;
- select a disk when more than one safe candidate exists;
- remove confirmation or validation to make a test pass;
- write an ISO to a block device without explicit user intent;
- commit private keys, passwords, tokens or plaintext secrets;
- fetch an unpinned mutable branch during installation;
- use mutable container tags such as `latest`.

Destructive installation must require:

- explicit invocation from the development PC;
- successful SSH connection;
- remote hardware discovery;
- safe disk validation;
- exclusion of removable and installer devices;
- explicit confirmation of the full disk path, unless running a disposable CI test with `--yes`.

Tests must use disposable qcow2 disks only.

## Working Style

Proceed incrementally.

For each change:

1. identify the smallest relevant test;
2. implement the change;
3. format it;
4. run the narrow test;
5. run broader checks when practical;
6. document unresolved assumptions.

Do not generate the entire repository without testing intermediate layers.

Do not silently replace the requested architecture.

Before implementation, define the interfaces between rescue delivery, SSH transport, discovery JSON, disk selection, runtime disk override, `nixos-anywhere`, and verification.

## Tooling

Prefer the development shell:

```bash
nix develop
```

Primary commands:

```bash
nix fmt
nix flake show
nix flake check --print-build-logs
nix build .#rescue-iso --print-build-logs
nix run .#discover -- root@HOST
nix run .#install -- --target root@HOST --host HOST_CONFIG
```

Use `just` tasks when available.

Install host-level packages only when required to install or operate Nix itself.

## Nix Conventions

- Use flakes.
- Commit `flake.lock`.
- Use one formatter.
- Keep modules small and focused.
- Separate reusable services from rescue and disk logic.
- Prefer a generic hardware module.
- Parameterize the target disk.
- Prefer declarative NixOS configuration over shell.
- Keep `system.stateVersion` stable.
- Review lock-file updates.
- Add assertions for required or dangerous options.
- Do not edit tracked configuration merely to insert a runtime disk path.

## Shell Conventions

Every non-trivial Bash script must begin with:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
```

Requirements:

- quote variables;
- use cleanup traps;
- use explicit timeouts;
- print actionable errors;
- pass ShellCheck;
- never parse `ls`;
- use `lsblk --json` where practical;
- never guess a block device;
- log every destructive decision;
- keep discovery scripts read-only.

## Python Conventions

- Target Python 3.14 from the pinned Nixpkgs input. Do not reduce the runtime version
  merely because a formatter exposes only a Python 3.13 parser flag.
- Keep the installable package under `python/`, use `pyproject.toml`, and commit
  `python/uv.lock` after reviewing dependency changes.
- Prefer the standard library when it is clear and sufficient. Add a modern typed
  dependency only for a concrete need; do not add configuration libraries when there
  is no configuration model to load.
- Use type hints, focused modules, detailed docstrings, and argparse manuals for every
  operator-facing command.
- Keep safety policy in pure functions. Keep subprocess calls argument-vector based;
  never use `shell=True` for locally constructed commands.
- Test pure policy with realistic fixtures and process boundaries with temporary files
  or executable fixtures. Prefer integration-style tests over extensive mocking.
- Run `just fmt`, `just lint`, and `just test-python` for Python changes. Ruff, Black,
  pytest, coverage, and pre-commit configuration are mandatory CI inputs.
- For local setup, create `./venv` with `python3 -m venv ./venv`, install UV into it,
  then run `./venv/bin/uv sync --project python --active`.

## Rescue ISO Requirements

The shared rescue system must:

- be generic x86_64 UEFI;
- use Ethernet DHCP;
- expose SSH;
- authorize a public key;
- optionally expose mDNS;
- include diagnostic tools;
- print connection information;
- contain no automatic disk installation service.

Tests must prove that booting the ISO does not modify the target disk. When PXE support is implemented, the same requirement applies to PXE boot.

## Hardware Discovery Requirements

Discovery must collect:

- DMI vendor and product;
- block devices;
- stable by-id links;
- transport and removable flags;
- mount points;
- network interfaces and addresses;
- PCI and USB devices.

Discovery must:

- produce machine-readable JSON;
- make no changes;
- avoid committing hardware reports automatically;
- clearly identify candidate disks.

## Disk Selection Rules

Automatic selection is allowed only when exactly one candidate remains after excluding:

- removable devices;
- USB transport;
- the rescue media;
- mounted disks;
- unsupported device types.

When multiple candidates remain, fail and require `--disk`.

Prefer `/dev/disk/by-id/...`.

Interactive installation must require the user to type the full selected path.

## Remote Installation Requirements

Use pinned `nixos-anywhere` and `disko`.

The install command must:

1. verify SSH;
2. run discovery;
3. select or validate disk;
4. print destructive summary;
5. confirm;
6. generate a temporary disk override module;
7. install the selected host configuration;
8. wait for reboot;
9. verify SSH;
10. verify services and application health.

The install command must not modify tracked files.

## WSL2 Rules

Assume Ubuntu in WSL2.

- Keep the repository in the Linux filesystem.
- Detect systemd.
- Do not assume raw USB access.
- Do not assume KVM.
- Prefer shared router or switch networking for the real mini PC.
- Keep fast local checks useful when full E2E runs only in CI.

## Testing Requirements

Maintain these layers:

1. formatting and flake evaluation;
2. target closure builds;
3. service VM tests;
4. disk-layout tests;
5. rescue ISO VM test;
6. PXE/iPXE boot test when that output is implemented;
7. full remote-provisioning E2E.

Service tests must verify:

- SSH active;
- password authentication disabled;
- root login disabled;
- Docker active;
- application service active;
- application health succeeds.

Rescue ISO tests must verify:

- DHCP;
- SSH;
- diagnostic tools;
- no auto-install service;
- no disk changes.

E2E must test:

- the actual shared rescue system through at least the ISO delivery path;
- SSH connection;
- discovery;
- safe disk selection;
- remote install;
- reboot;
- installed-system SSH;
- application health.

When KVM is unavailable, use TCG or delegate the full E2E to CI with a clear message.

## Security

Public SSH keys may be committed deliberately.

Never expose:

- SSH private keys;
- age private identities;
- GitHub credentials;
- VPN enrollment keys;
- registry credentials;
- application secrets.

Values referenced by Nix derivations may enter the Nix store.

Before adding secrets, propose a threat model and prefer `sops-nix`.

## Containers

- Pin images by digest.
- Do not use `latest`.
- Add health checks.
- Keep persistent data outside immutable Nix store paths.
- Document volumes and backups.
- Validate Compose in CI.
- Treat Docker group membership as root-equivalent.

## GitHub Actions

- Use minimal permissions.
- Pin finalized third-party Actions to commit SHAs.
- Set timeouts.
- Upload logs on failure.
- Keep production secrets out of ISO jobs.
- Make full E2E manually runnable.
- Use a self-hosted KVM runner if hosted TCG is too slow.

## Documentation

Update `README.md` when commands, behavior, safety gates or assumptions change.

Use exact paths and runnable commands.

Use visible placeholders:

```text
REPLACE_WITH_REAL_PUBLIC_KEY
REPLACE_WITH_VERIFIED_DIGEST
```

Do not fabricate values.

## Stop Conditions

Stop and report clearly when:

- an operation could erase a non-disposable host disk;
- multiple candidate disks remain and no explicit disk was supplied;
- a private credential would need to be committed;
- a proposed test targets the host rather than a qcow2 disk;
- a safety assertion fails;
- unrelated user changes would be overwritten.

Do not stop merely because implementation is complex. Complete all non-destructive scaffolding and tests that can be completed safely.
