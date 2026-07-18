# Generic NixOS mini-PC provisioning

This repository provisions x86_64 UEFI mini PCs through a shared, non-destructive
NixOS rescue environment. The Lenovo ThinkCentre M710q (10MQ) is the first target,
but the host and rescue configurations deliberately contain no Lenovo disk ID, DMI
gate, interface name, or autonomous installer.

> **Disk safety:** booting rescue never installs anything. Only the explicit remote
> `install` command can erase a disk. It fails unless discovery identifies one safe
> disk or the operator supplies a validated `/dev/disk/by-id/...` path, and interactive
> use requires typing that complete path.

## Architecture contract

```text
USB ISO | PXE/iPXE | QEMU
          |
          v
shared rescue system (DHCP, SSH, diagnostics; no installer service)
          |
          v  SSH must already work
discovery JSON 1.0 (read-only snapshot)
          |
          v
selector (one stable safe path or fail closed)
          |
          v
temporary untracked disk/key module -> pinned nixos-anywhere + disko
          |
          v
reboot -> admin SSH -> systemd/Docker/HTTP verification
```

The delivery method ends at SSH readiness. Discovery and installation do not inspect
whether rescue arrived through USB, PXE, or QEMU. The interfaces are:

- `mini-pc-provision discover [--output FILE] [--port PORT] [--identity FILE] user@host`
  writes discovery schema `1.0`, prints only the report path on stdout, and reports
  candidates on stderr.
- `mini-pc-provision select-disk [--disk /dev/disk/by-id/...] REPORT.json` prints exactly one stable
  path on success. It excludes removable, USB, mounted, unsupported, and unstable-path
  disks; zero or multiple candidates are errors.
- `mini-pc-provision install --target root@HOST --host NAME --admin-key-file PUBLIC_KEY [...]` reruns
  discovery, selection, and confirmation, then re-discovers and compares the stable
  path, aliases, model, serial, size, and mount state immediately before creating a
  temporary wrapper flake. `--yes` requires `--ci-disposable`, `CI=true`, QEMU DMI,
  host `e2e-target`, and the exact `virtio-nixos-e2e` identity. Tracked configuration
  is never edited, and rescue SSH host keys are copied across the reboot.
- `mini-pc-provision provision` composes prerequisite, temporary-network, readiness,
  discovery, selection, installation, verification, and cleanup stages. Supporting
  stages remain independently callable through their documented subcommands.
- `mini-pc-provision verify-installed --target admin@HOST [...]` checks SSH, `sshd`, Docker, the
  Compose unit, and HTTP health.

Discovery reports contain DMI strings, serial numbers, network addresses, PCI/USB
lists, mounts, block topology, and by-id mappings. They are mode 0600 under
`artifacts/discovery/` and ignored by Git. Do not commit them casually.

See [the repository layout](docs/REPOSITORY_LAYOUT.md) for the distinction between
configuration, examples, generated outputs, and private local files. See
[the command reference](docs/SCRIPTS.md) for the operator-facing scripts.

## Bootstrap on Ubuntu/WSL2

Keep the checkout in the Linux filesystem, not `/mnt/c`. Verify WSL and systemd:

```bash
grep -i microsoft /proc/sys/kernel/osrelease
ps -p 1 -o comm=
```

If PID 1 is not systemd, set `[boot] systemd=true` in `/etc/wsl.conf`, run
`wsl --shutdown` from PowerShell, and restart Ubuntu. Install Nix using the official
multi-user installer, then enable `nix-command flakes` in `/etc/nix/nix.conf`.
Host-level bootstrap packages are `curl`, `git`, `xz-utils`, `ca-certificates`, and
`jq`; the flake development shell supplies project tools:

```bash
nix develop
just check-fast
```

The provisioning implementation targets Python 3.14 and lives in `python/`. For the
preferred local virtual environment in the repository root:

```bash
python3 -m venv ./venv
./venv/bin/python -m pip install uv
./venv/bin/uv sync --project python --active
./venv/bin/pytest -c python/pyproject.toml
```

`uv.lock` pins development dependencies. Runtime provisioning intentionally uses only
the Python standard library and external tools supplied by Nix; no environment library
is added because the commands have no application configuration to deserialize. Run
`mini-pc-provision --help` and each subcommand's `--help` for detailed manuals.

This repository pins NixOS 25.11, disko, and nixos-anywhere in `flake.lock`. Review any
lock update before committing it.

## Configure public keys

Private keys, passwords, tokens, and secrets must never be committed. Copy only a real
public key to a local path, for example `~/.ssh/id_ed25519.pub`. Build an SSH-accessible
rescue ISO without changing tracked files:

```bash
scripts/build-iso.sh ~/.ssh/id_ed25519.pub
```

The raw `nix build .#rescue-iso` output intentionally has no invented key and is useful
for evaluation/tests only; do not use it for a headless physical boot. The installer
requires `--admin-key-file` and injects that public key into the installed system.
The rescue key permits temporary `root` access; the admin key permits routine access
to the installed non-root `admin` account. They may be the same public key, but their
roles and rotation scopes differ.

## Application secrets

Plaintext secrets must not be referenced by Nix because Nix store objects are not
secret. The installer can instead copy a root-only Compose environment file directly
to the installed filesystem:

```bash
scripts/create-secrets-file.sh --name DATABASE_PASSWORD --name API_TOKEN
nix run .#install -- ... --application-env-file secrets/compose.env
```

Read [the secrets threat model and workflow](docs/SECRETS.md) before adding a service
that needs credentials.

## Development and tests

```bash
nix develop
just fmt
just test-python
just check-fast
nix flake check --print-build-logs
nix build .#rescue-iso --print-build-logs
nix build .#pxe-bundle --print-build-logs
just pxe-test
```

Checks cover formatting/evaluation, ShellCheck, selector fixtures, target closures,
Compose and workflow validation, the real disko layout on a disposable VM disk,
services and SSH policy, and shared rescue behavior including a before/after
target-disk hash. The full E2E builds a key-injected ISO, boots it with OVMF UEFI and
QEMU, verifies an unchanged raw disk, discovers and selects it, runs nixos-anywhere,
reboots from the installed disk, then checks SSH and HTTP:

```bash
nix develop -c timeout 100m tests/e2e/run.sh
```

KVM is used when writable; otherwise QEMU TCG is selected and can be very slow. WSL2
does not reliably expose raw USB devices. Full E2E is mandatory in GitHub Actions and
may be skipped locally when KVM or time is unavailable, while fast checks should still
run.

## Direct Ethernet provisioning

The primary transport is one dedicated cable between development PC and target. It
uses only the isolated `192.168.77.0/24` network: the PC owns `192.168.77.1`, and the
rescue receives `192.168.77.2` from temporary DHCP.

Isolation prevents the temporary DHCP server from competing with a home router. The
orchestrator rejects the default-route interface, virtual interfaces, ambiguous
physical NICs, an existing global IPv4 address, and any local UDP/67 listener. It does
not rewrite router, Windows, or persistent host network configuration. The Lenovo
needs no Internet access: TFTP/HTTP serve pinned rescue artifacts locally, and
`nixos-anywhere` copies the built installation closure over SSH.

Review the dedicated interface with `ip -brief link`, connect the cable, enable UEFI
PXE in firmware, and run from the repository. Root is required for DHCP/TFTP and
temporary interface addressing:

```bash
sudo -E just -- provision-m710q \
  --interface REPLACE_WITH_DEDICATED_ETHERNET
```

When a Linux PXE host runs in a bridged VM, the physical Windows adapter may also
request the single DHCP lease. Exclude that adapter at runtime without persisting its
machine-specific address in the repository:

```bash
sudo -E just -- provision-m710q \
  --interface REPLACE_WITH_DEDICATED_ETHERNET \
  --ignore-client-mac REPLACE_WITH_WINDOWS_ADAPTER_MAC \
  --target-mac REPLACE_WITH_TARGET_MAC
```

The exclusion option is repeatable. `--target-mac` reserves `192.168.77.2` for the
reviewed target and prevents another bridged client from consuming the only lease.
Each value must be a colon-separated MAC address and is written only to the private
session's temporary dnsmasq configuration.

The command builds a key-authorized PXE bundle from pinned inputs, optionally sends
Wake-on-LAN with `--wake-mac`, waits for rescue SSH, displays disk identity, requires
the full stable path, installs, and verifies SSH, Docker, the Compose unit, and HTTP.
Installation reboot is deliberately deferred until the temporary network switches
from PXE/TFTP/HTTP delivery to DHCP-only mode. This lets PXE-first firmware fall
through to the installed disk while retaining the fixed address for verification.
Rescue and installed SSH identities use a private per-session trust file that is reset
at this transition. All temporary network services and the owned address are stopped
after success or failure.
When all three key flags are omitted, it creates and reuses
`~/.ssh/mini_pc_provision_ed25519` for the invoking user, including when run through
`sudo`. To use existing credentials, pass `--identity`, `--rescue-key-file`, and
`--admin-key-file` together. Private keys are never written under the repository.

Every attempt creates a private ignored directory under `artifacts/sessions/` with
metadata, environment, prerequisite/network/readiness reports, `discovery.json`,
`selected-disk.json`, installation and verification reports, a provisioning log, and
a best-effort journal. Failed sessions remain available; cleanup never removes them.

On the current WSL2 setup only the WSL default-route `eth0` is visible; the Windows
cable adapter is not exposed as an independent Linux NIC. The safety policy therefore
refuses physical direct-cable DHCP from this WSL instance. Use native Linux, an
explicit Windows networking arrangement outside this repository, or another Linux
PXE host. `just pxe-test` still works in WSL by using a disposable TAP only.

Home-LAN transport remains future work. Until a separate backend exists, use the
low-level `discover` and `install` commands with a router-provided address; never start
the direct-Ethernet DHCP backend on an existing LAN.

## Physical installation

One local firmware session may be needed to enable UEFI USB/PXE boot and choose boot
priority. This design does not rely on AMT, vPro, remote KVM, or remote ISO redirection.
Wake-on-LAN can be configured later but cannot select a boot device.

1. Build the key-authorized ISO with `scripts/build-iso.sh`.
2. Write it from native Linux with the guarded command below, or use a trusted Windows
   image writer. Never assume raw USB access from WSL.
3. Boot the target, wait for DHCP, then connect as root over SSH.
4. Run discovery and review the JSON and candidate summary.
5. Run install and type the complete selected by-id path.

```bash
scripts/write-usb.sh "$(find -L result/iso -name '*.iso' -print -quit)" /dev/REVIEWED_USB_DEVICE

nix run .#discover -- root@nixos-rescue.local

nix run .#install -- \
  --target root@nixos-rescue.local \
  --host m710q \
  --admin-key-file ~/.ssh/id_ed25519.pub \
  --identity ~/.ssh/id_ed25519 \
  --installed-target admin@m710q.local
```

If multiple safe internal disks remain, discovery succeeds but installation stops.
Review the report and repeat with `--disk /dev/disk/by-id/REVIEWED_ID`. Never substitute
`/dev/sda`.

The installed service listens on `http://HOST:8080/`. Its nginx image is pinned by
registry digest. Application state belongs under `/var/lib/mini-pc`; see
`application/README.md` for backup and secret guidance. Docker group membership is not
granted because it is root-equivalent.

## PXE/iPXE

`nix build .#pxe-bundle` generates pinned `ipxe.efi`, separate TFTP and HTTP roots,
a store-path-correct iPXE script, and a hash manifest from the same rescue module. See
`pxe/README.md`. CI boots the complete UEFI/DHCP/TFTP/iPXE/HTTP path, reaches SSH and
discovery, and proves the disposable target disk unchanged. The dnsmasq example never
rewrites host or router DHCP configuration.

The M710q (10MQ, Pentium G4400T) has no AMT, vPro, remote KVM, or remote BIOS in this
design. Wake-on-LAN is optional and cannot choose a boot device. The preferred order
is Network/PXE, USB, internal SSD, based on current target testing that absent PXE
falls through; validate the exact firmware before relying on it. USB, internal SSD,
PXE remains the conservative alternative.

## CI and releases

`check.yaml` runs flake and VM checks and builds both rescue deliveries.
`provisioning-e2e.yaml` runs the actual disposable remote provisioning flow with a
strict timeout and uploads logs. `release-iso.yaml` creates a draft release only for
tags and requires the repository variable `RESCUE_SSH_PUBLIC_KEY`; it contains a public
key by design and no production secret. Third-party Actions are pinned to full commit
SHAs and workflows use minimal permissions.
