# Architecture

## Scope

The repository turns a pinned Git revision into a reproducible NixOS installation for
generic x86_64 UEFI mini PCs. The ThinkCentre M710q is the first deployed host, not a
hardware gate. Machine-specific disk identifiers, interfaces, DMI strings, and private
credentials are runtime inputs rather than committed configuration.

## Provisioning boundaries

Delivery, transport, and provisioning are separate concerns:

| Layer | Implemented choices | Contract boundary |
| --- | --- | --- |
| Rescue delivery | USB ISO, PXE/iPXE, QEMU | shared rescue reaches DHCP and SSH without writing a disk |
| Transport | isolated direct Ethernet; operator-managed LAN SSH | an explicit SSH target is reachable |
| Provisioning | discovery, disk selection, nixos-anywhere, verification | structured reports and validated command inputs |

The rescue system in `rescue/system.nix` is shared by thin ISO and PXE wrappers. It
contains diagnostic tools and an injected public key but no installation service.
Booting any rescue output is therefore non-destructive.

Discovery schema `1.0` records DMI, block topology and stable aliases, mounts, network
addresses, PCI, and USB data. The selector excludes removable, USB-transport,
mounted, unsupported, and unstable-path disks. Automatic selection succeeds only for
one remaining candidate. Installation repeats identity and mount checks immediately
before invoking pinned `nixos-anywhere` and `disko`, and writes runtime disk/key
overrides only into temporary untracked flakes.

The high-level `provision` command composes independently callable stages and creates
an ignored session directory containing structured reports and logs. Cleanup always
stops only services and addresses owned by that session; evidence remains available
after success or failure.

## Installed system

Reusable NixOS modules own hardware defaults, the single-disk UEFI layout, SSH,
networking, Docker, applications, monitoring, security, and persistent journaling.
The generic profile does not enable LAN applications with placeholder policy. The
M710q profile supplies its reviewed hostname and source CIDR.

SSH permits the non-root `admin` user with public-key authentication and passwordless
sudo needed by the deployment boundary. Root and password login are disabled. No user
is added to the root-equivalent Docker group.

Application images are selected by immutable registry digests and Nix fixed-output
hashes, copied in the Nix closure, loaded locally, and started with `pull_policy:
never`. Actual binds only to host loopback. The optional Discord bot has no inbound
port and receives its validated environment from a root-owned runtime file outside
the Nix store.

## LAN web services

Caddy is the only LAN-facing application proxy. nftables accepts each HTTPS listener
only from explicitly configured IPv4 or IPv6 CIDRs.

| Origin | Backend | Reason |
| --- | --- | --- |
| `https://think-centre.home/` | Actual on `127.0.0.1:5006` | stable primary application origin |
| `https://think-centre.home:8443/` | Netdata on `127.0.0.1:19999` | isolates monitoring from Actual's root service worker |

Path routing was rejected for monitoring after physical Firefox testing. Actual's
service worker controls the entire port-443 origin and treats unknown navigations as
application routes, so `/status/` can become `/budget` without reaching Caddy. A
different port is a different browser origin and preserves Netdata's assumption that
it is hosted at `/`. The legacy path is only a redirect for clients whose service
worker does not intercept it.

Caddy uses its internal CA. Operators verify the CA fingerprint over SSH before
installing the root certificate on clients. No router forwarding, UPnP publication,
cloud tunnel, or public DNS exposure is part of the configuration.

## Monitoring decision

Netdata was selected for the MVP because the pinned NixOS package provides a useful
local dashboard, historical storage, host collectors, and lm-sensors integration in
one service. A Prometheus/Grafana stack would provide greater long-term flexibility
at substantially higher operational cost; Beszel and Glances were smaller but less
aligned with the required historical host detail; a custom dashboard would create an
unnecessary application maintenance surface.

The agent is unclaimed, analytics-disabled, and loopback-only. It runs as a dedicated
unprivileged user without Docker membership, Docker socket discovery, privileged
debugfs, or unused collector families. Retention is bounded by time and a dbengine
size target. The narrow Nixpkgs unfree predicate exists because the bundled Netdata UI
uses NCUL1; it does not permit unrelated unfree packages.

## Deployment boundary

`mini-pc-provision deploy` is the only supported full-update path for an installed
host. It performs read-only preflight, builds a key-preserving generation locally,
copies it through authenticated remote sudo, optionally stages validated secrets,
takes an Actual backup, requests exact target confirmation, activates, and runs every
health helper present in the candidate generation. On failure it collects diagnostics
and restores the validated previous generation and secret files. Generations and
images are never pruned as part of deployment.

Secret-only mode uses the same validation and atomic staging policy but does not build
or activate NixOS. Its confirmation bypass, like installation's bypass, is restricted
to an explicit disposable localhost CI context.

## Reproducibility and secrets

`flake.lock` pins NixOS, disko, and nixos-anywhere. Container manifests and archives
are immutable. Runtime provisioning does not fetch mutable branches. Public SSH keys
may be intentionally supplied to builds; private keys and application credentials may
not enter Git, Nix expressions, derivations, command arguments, or logs.

Actual data, Caddy state, secrets, backups, and monitoring history live under mutable
host paths rather than the Nix store. NixOS generations reproduce software and policy,
not application data. Backup and secret recovery are separate operational concerns.
