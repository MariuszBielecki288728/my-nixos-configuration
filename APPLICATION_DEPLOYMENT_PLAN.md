# Application and NixOS Deployment Implementation Plan

## 1. Purpose and status

This document is an implementation plan only. It does not enable services, open
ports, change the installed Lenovo, or contain production credentials.

The goal is to replace the demonstration nginx Compose stack with a reproducible,
LAN-only application platform containing:

- Actual Budget;
- actual-ai, using Ollama as its local LLM provider;
- Ollama and one explicitly selected local model;
- `MariuszBielecki288728/actual-discord-bot`;
- a safe deployment utility that can update the Compose stack, runtime secrets, and
  the complete NixOS configuration on both fresh and existing installations.

The same desired state must be used during initial provisioning and subsequent
updates. Rescue delivery remains independent from application deployment, and no
rescue image or PXE boot may start an installation automatically.

## 2. Scope

### In scope

- Refactor the current single-image Compose/Nix integration into a multi-service
  application stack.
- Package every container image reproducibly and pin immutable inputs.
- Keep all application endpoints private to the host or trusted LAN.
- Provide HTTPS for Actual without making it Internet-accessible.
- Define persistent storage, health checks, upgrades, backup, restore, and rollback.
- Define a secrets workflow for first installation and later rotation.
- Add one operator command for complete NixOS deployments and a narrow mode for
  secret-only updates.
- Test the stack in disposable VMs before deploying it to the physical Lenovo.
- Document the external work needed to publish or reproducibly build the Discord
  bot image.

### Out of scope for this change

- Implementing the services described here.
- Creating real credentials, Actual budget IDs, Discord tokens, or encryption keys.
- Choosing a LAN CIDR, hostname, or fixed address without inspecting the real LAN.
- Enabling router port forwarding, UPnP, cloud tunnels, or public DNS.
- Automatically selecting an Ollama model before checking the Lenovo's installed
  memory, free storage, and real inference performance.
- Moving installation logic into the rescue system.

## 3. Sources and planning snapshot

The implementation must re-check upstream releases when work starts. At the time
this plan was written (2026-07-19), the upstream release snapshot was:

| Component | Planning baseline | Production pinning rule |
| --- | --- | --- |
| Actual Budget | `v26.7.0` | Select the then-current stable release, review its notes, and pin its linux/amd64 image by registry digest and Nix fixed-output hash. |
| actual-ai | `2.4.2` | Select a release compatible with the chosen Actual version and pin its image by digest and Nix hash. |
| Ollama | `v0.32.1` | Select a tested release and pin its image by digest and Nix hash. |
| actual-discord-bot | `main` at `8d987b24371e87de698581916d46ac2d45ad42d4` | Use a released image digest or an exact source commit; never build production from a floating branch. |
| Ollama model | Not selected | Select after hardware validation and pin an explicit model identifier; record its size and checksum/digest where supported. |

Relevant sources:

- [Existing personal Actual Compose configuration](https://github.com/MariuszBielecki288728/actual-budget-config/blob/main/docker-compose.yml)
- [Actual Budget repository and releases](https://github.com/actualbudget/actual)
- [Actual HTTPS documentation](https://actualbudget.org/docs/config/https/)
- [Actual reverse-proxy documentation](https://actualbudget.org/docs/config/reverse-proxies/)
- [actual-ai repository and configuration](https://github.com/sakowicz/actual-ai)
- [Ollama repository](https://github.com/ollama/ollama)
- [Ollama model-pull API](https://docs.ollama.com/api/pull)
- [actual-discord-bot repository](https://github.com/MariuszBielecki288728/actual-discord-bot)

The old Compose file is useful as a functional inventory, but its mutable `latest`
tags, host-published Ollama port, and `pull_policy: always` must not be carried into
this repository.

## 4. Target architecture

```text
trusted LAN client
    |
    | HTTPS 443 (source restricted to configured LAN CIDR)
    v
native NixOS Caddy
    |
    | 127.0.0.1:5006 only
    v
Actual server ---- private Compose network ---- actual-ai
                                              |       |
                                              |       +---- Ollama :11434
                                              |
                                              +---- Actual internal URL

Discord API <---- outbound TLS ---- actual-discord-bot
                                  |
                                  +---- Actual internal URL
```

Only Caddy is reachable from the LAN. Actual binds a published port to loopback so
the host-native reverse proxy can reach it. actual-ai, Ollama, the Ollama model-init
job, and the Discord bot have no host-published ports. SSH remains governed by the
existing NixOS administration policy.

Use native NixOS Caddy rather than another Compose container because it avoids a
Docker-socket dependency, integrates cleanly with the host firewall, and can start
independently from the application stack. Caddy should use its internal CA for the
LAN hostname unless an already trusted private PKI is supplied. Client devices must
trust that CA; otherwise Actual's browser features that require a secure context may
not work correctly despite the service being confined to a LAN.

No router port forwarding is part of this design. The deployment documentation must
state that explicitly.

## 5. Configuration interfaces

Define interfaces before implementation so initial installation and later updates
use exactly the same inputs.

### 5.1 Non-secret NixOS options

Add a focused application module with options conceptually equivalent to:

```nix
my.actualStack = {
  enable = true;
  hostname = "REPLACE_WITH_LAN_HOSTNAME";
  trustedLanCidrs = [ "REPLACE_WITH_LAN_CIDR" ];
  dataRoot = "/var/lib/mini-pc";
  actualLoopbackPort = 5006;
  ollamaModel = "REPLACE_WITH_TESTED_MODEL";
};
```

Do not commit the placeholders as an enabled production configuration. Add
assertions that reject an enabled stack with placeholders, an empty trusted-CIDR
list, non-loopback Actual binding, mutable image tags, or missing immutable image
metadata.

The trusted-LAN setting must support reviewed IPv4 and IPv6 CIDRs. If IPv6 policy is
not configured, the service must not become reachable through an unrestricted IPv6
listener.

### 5.2 Runtime secret contract

The minimum secret inventory is expected to include:

- `ACTUAL_PASSWORD`;
- `ACTUAL_BUDGET_ID` or the exact upstream variable required by the selected
  actual-ai release;
- `ACTUAL_E2E_PASSWORD` when the budget uses end-to-end encryption;
- `DISCORD_TOKEN`;
- Discord bank and receipt channel IDs;
- the Discord bot's Actual password, budget/file identifier, encryption password,
  account identifier, and OCR settings where required.

During implementation, normalize names only where a wrapper maps them explicitly.
Do not assume that actual-ai and the Discord bot use identical variable names.

Secrets must never be placed in Git, Nix expressions, derivations, image layers,
process command lines, or CI logs. Root and a container receiving a secret can still
read it; the threat model does not claim to protect against a compromised host root
or compromised application container.

The initial deployment may continue to accept a mode-0600 dotenv file as an attended
bootstrap path. The target long-term design is `sops-nix` with an age identity stored
outside Git and with a documented recovery copy. Before enabling `sops-nix`, decide:

1. where the host age identity is generated and backed up;
2. which operator identities may decrypt production secrets;
3. whether CI can evaluate/build without decryption;
4. how a lost machine is recovered;
5. how secret rotation and rollback interact.

Prefer per-service credential files when upstream images support them. Until they do,
Compose environment variables remain visible to host root through Docker inspection.

### 5.3 Image inventory

Refactor `my.application.image` into a typed image inventory. Each image entry should
carry:

- Compose service/image name;
- immutable registry reference containing a digest;
- linux/amd64 archive source;
- Nix fixed-output hash;
- optional upstream version label for operator readability.

Generate one deterministic image-loading unit or script from this inventory. Compose
must use `pull_policy: never`, and the installed machine must not need registry access
to start or restart the stack.

## 6. Compose refactor

### 6.1 Repository layout

Refactor the demo layout toward:

```text
application/
  compose.yaml
  README.md
  config/
    README.md
modules/
  application.nix
  actual-stack.nix
docs/
  APPLICATION_OPERATIONS.md
  BACKUP_AND_RESTORE.md
  SECRETS.md
```

Keep Compose as the service topology and NixOS as the owner of host directories,
permissions, firewall rules, reverse proxy, image archives, and systemd lifecycle.
Do not generate secrets into the Nix store while rendering Compose.

### 6.2 Actual server

- Use the current reviewed stable Actual release, not `latest`.
- Pin the image by digest and Nix fixed-output hash.
- Mount persistent data at `/data` from
  `/var/lib/mini-pc/actual/data`.
- Publish `5006` only on `127.0.0.1`; do not bind it to all interfaces.
- Add the upstream-supported health check.
- Join only the application network needed by actual-ai and the bot.
- Run with `no-new-privileges`, dropped capabilities, and a read-only root filesystem
  where the tested image permits it.
- Configure Caddy's reverse-proxy headers according to Actual's current documentation
  and verify that COOP/COEP headers are present exactly once.

### 6.3 actual-ai

- Use a release tested against the selected Actual version and pin its image.
- Use the selected release's current Ollama interface, expected to include
  `LLM_PROVIDER=ollama`, an explicit `OLLAMA_MODEL`, and an internal URL such as
  `http://ollama:11434/api`; verify exact variable names upstream.
- Connect to Actual using its internal Compose service URL, never the LAN URL.
- Do not publish an actual-ai port.
- Start with non-destructive behavior: enable its dry-run feature for acceptance
  testing, inspect proposed classifications, and only then deliberately enable writes.
- Make optional features such as account sync, category suggestions, and web search
  explicit. Do not enable outbound web-search features by accident.
- Define a health check and bounded restart policy.

### 6.4 Ollama

- Pin the Ollama server image and keep port `11434` internal to Compose.
- Persist model data under `/var/lib/mini-pc/ollama`.
- Add a health check that verifies the local API without downloading anything.
- Add a one-shot `ollama-model-init` service that waits for health and invokes the
  official model-pull API for the configured model.
- Make model download an explicit deployment phase with progress, timeout, disk-space
  preflight, and an actionable error. A transient model download failure must not
  roll back a working Actual server.
- Do not back up the model cache by default; it is reproducible and can be downloaded
  again.

Before selecting a model, record `free -h`, CPU details, free space, and a representative
classification benchmark on the physical M710q. The Pentium G4400T is CPU-only for
this design, so start evaluation with a small quantized model recommended by the
selected actual-ai release. Accept the model only after measuring latency and peak
memory without forcing the host into swap or OOM. Keep the model configurable so an
upgrade does not require restructuring the stack.

### 6.5 actual-discord-bot

- Use the production target from the bot repository and an exact source revision.
- Prefer adding a bot-repository release workflow that publishes a linux/amd64 image
  to GHCR, with SBOM/provenance and an immutable digest. This configuration repository
  then consumes that digest just like other images.
- If publishing is not yet available, build the bot image reproducibly from a pinned
  flake source or exact commit. Never clone `main` during deployment.
- Configure `ACTUAL_URL` with the internal Actual service URL.
- Supply Discord and Actual credentials only at runtime.
- Do not publish a host port.
- Retain Polish Tesseract/OCR support from the existing production image unless the
  bot's requirements change.
- Add a health/readiness mechanism. If the bot has no HTTP health endpoint, add a
  minimal application-level check or systemd watchdog rather than treating a running
  container process as sufficient proof.
- Verify reconnect behavior, Discord rate-limit handling, duplicate-message behavior,
  bank notification processing, receipt image OCR, and receipt PDF processing.

### 6.6 Container hardening and resource policy

For each service, determine and document:

- required writable paths;
- non-root UID/GID support;
- dropped Linux capabilities;
- `no-new-privileges` compatibility;
- read-only root filesystem compatibility;
- temporary filesystem needs;
- memory/CPU limits and reservation behavior;
- graceful shutdown timeout;
- log size/rotation limits.

Do not apply a hardening flag blindly if it breaks the upstream image. Record each
exception. Ollama requires a writable model directory and will likely need the largest
resource allowance. Prevent its resource use from making SSH or Actual unavailable.

## 7. LAN-only networking and HTTPS

1. Inspect the real LAN and choose a stable hostname plus explicit trusted IPv4/IPv6
   CIDRs. Do not infer them from a temporary direct-Ethernet PXE network.
2. Configure a router DHCP reservation for the Lenovo if stable addressing is needed.
3. Bind Actual's published Compose port to `127.0.0.1` only.
4. Listen with Caddy on HTTPS `443` and redirect HTTP only if TCP `80` is also
   source-restricted to the trusted LAN.
5. Express source-CIDR filtering in the NixOS firewall/nftables configuration; merely
   listing an allowed TCP port is insufficient for LAN-only access.
6. Test allowed and denied source paths, including IPv6.
7. Install the Caddy internal root CA on each intended client and verify the Actual
   URL has a valid secure context.
8. Confirm the router has no port forward and the host does not advertise the service
   through UPnP or a tunnel.

The application should use a meaningful LAN hostname, not a bare IP, so certificates
and saved client URLs remain stable. mDNS may be used only after testing name resolution
on the intended clients.

## 8. Persistent data and ownership

Create host directories declaratively with explicit owner, group, and mode:

```text
/var/lib/mini-pc/actual/data       critical persistent data
/var/lib/mini-pc/ollama            reproducible model cache
/var/lib/mini-pc/caddy             Caddy state/CA material, if not using defaults
/var/lib/mini-pc/secrets           runtime secrets, root-only
/var/lib/mini-pc/backups/actual    local staged backups
```

Check the actual container UIDs before assigning ownership. Do not solve permission
problems with world-writable directories. If the Discord bot gains durable state,
give it a separate directory and backup classification rather than sharing Actual's
data directory.

## 9. Deployment utility

Extend the Python provisioning package with a separate operator-facing `deploy`
command. Keep installation and deployment policies in shared pure functions but do
not make deployment depend on rescue delivery.

Proposed interface:

```text
nix run .#deploy -- \
  --target admin@HOST \
  --host m710q \
  --identity ~/.ssh/id_ed25519 \
  --admin-key-file ~/.ssh/id_ed25519.pub \
  --application-env-file PATH

nix run .#deploy -- \
  --target admin@HOST \
  --identity ~/.ssh/id_ed25519 \
  --secrets-only \
  --application-env-file PATH
```

### 9.1 Full deployment flow

1. Validate local inputs and reject private keys passed as public-key inputs.
2. Verify SSH host identity and connectivity with an explicit timeout.
3. Collect a read-only remote preflight: NixOS generation, disk space, memory, Docker
   state, application health, and currently loaded image IDs.
4. Validate the dotenv/sops inputs without printing values.
5. Build the target system locally using the pinned flake.
6. Build/load all required image archives before stopping the old application.
7. Create a timestamped pre-upgrade Actual backup and verify it is non-empty.
8. Stage secrets in a mode-0700 temporary directory, then atomically install them as
   root-owned mode `0600` files outside the Nix store.
9. Inject the selected admin public key through a temporary, untracked Nix module so
   a full rebuild cannot remove the operator's only SSH access.
10. Copy and activate the new NixOS generation with a command-vector-based process;
    never construct a shell command from user input.
11. Wait for systemd, Compose, Actual health, HTTPS, actual-ai, and bot readiness.
12. Run a read-only application smoke test.
13. Mark the deployment successful and prune nothing automatically.
14. On failure, collect diagnostics, roll back to the prior NixOS generation and prior
    secret file, restart the prior stack, and report whether service was restored.

The tool must show a non-secret change summary and ask for confirmation before
activation. A CI/disposable-VM `--yes` mode may bypass confirmation; production use
must remain interactive unless the user deliberately opts into a separately designed
automation policy.

### 9.2 Secret-only flow

1. Verify SSH and validate the candidate secret file locally.
2. Copy it to a root-only temporary remote path.
3. Preserve the previous secret file as a root-only rollback copy.
4. Atomically replace the live file.
5. restart only affected services;
6. wait for their health checks;
7. restore the previous file and services if health fails.

Do not run `nixos-rebuild` in secret-only mode. Clearly report which services were
restarted without echoing variable names whose presence would itself be sensitive.

### 9.3 Initial installation integration

Retain `mini-pc-provision install --application-env-file`, but make it call the same
secret validation/staging policy used by `deploy`. After `nixos-anywhere` reboots,
reuse the same application verification code. Thus a new machine and an updated
machine converge on the same directories, image inventory, secret paths, systemd
units, and health criteria.

## 10. Upgrade policy

“Latest” means a reviewed update process, not a floating runtime tag:

1. Query official stable releases.
2. Review release notes, compatibility, database migration warnings, and image
   architecture.
3. Resolve the manifest-list digest and linux/amd64 image digest.
4. Update the human-readable version, immutable registry reference, and Nix hash in
   one pull request.
5. Build image archives and run VM tests.
6. Back up Actual and test restoration.
7. Deploy to the physical host with health monitoring.
8. Keep the prior NixOS generation and data backup until the new version has been
   observed successfully.

Use a dependency updater only if it opens reviewable pull requests and cannot silently
activate production. Never use `latest`, an unpinned Git branch, or `pull_policy:
always`.

Database migration may make a container rollback insufficient. Treat Actual backup
and restore compatibility as a release-specific gate.

## 11. Backup and restore plan

Classify `/var/lib/mini-pc/actual/data` as critical. Before the first production
deployment, implement and test:

- a scheduled, root-only backup service and timer;
- a pre-upgrade backup invoked by the deployment tool;
- bounded retention;
- encrypted off-machine copy;
- integrity verification;
- an operator restore command with an explicit target and confirmation;
- a disposable-VM restore drill that starts Actual and verifies data readability.

Prefer an upstream-supported consistent backup method. If file-level copying is used,
stop/quiesce Actual or use a proven snapshot method so database files are consistent.
Do not run `docker compose down -v` in operational instructions.

Back up secrets only in an encrypted password manager or encrypted recovery bundle.
Do not include the Ollama model cache in routine backups unless bandwidth constraints
justify it. Preserve Caddy CA recovery material if clients depend on that CA.

## 12. Testing strategy

### 12.1 Static and evaluation tests

- `nix fmt` and Python formatting/linting.
- `nix flake show` and `nix flake check --print-build-logs`.
- Compose schema/config validation with secrets supplied by non-production fixtures.
- Assertions rejecting mutable image references, unrestricted binds, placeholders,
  and missing LAN policy.
- Tests for pure deployment policy, secret validation, rollback selection, and image
  inventory rendering.
- ShellCheck for any new shell scripts.

### 12.2 NixOS service VM tests

Use disposable VM disks and fixture secrets. Verify:

- SSH remains key-only and root login remains disabled;
- Docker, Caddy, and application systemd units are active;
- all images are preloaded and the stack starts with registry access unavailable;
- Actual is healthy through HTTPS;
- Actual is not reachable directly from the VM's LAN interface on port `5006`;
- Ollama and actual-ai have no host listener;
- only trusted test-LAN sources can reach HTTPS;
- persistent data survives a service and VM restart;
- secrets are absent from the Nix store and world-readable paths;
- dry-run actual-ai can reach both Actual and Ollama;
- the model-init job is idempotent;
- the bot can start with a fake Discord boundary or purpose-built integration fixture;
- resource pressure from Ollama does not make SSH and Actual unhealthy.

Avoid contacting real Discord or production Actual data from CI.

### 12.3 Deployment integration tests

In a disposable two-generation VM scenario, verify:

1. initial install receives the same secret layout;
2. a no-op deployment changes nothing;
3. a Compose/image update activates successfully;
4. secret-only rotation restarts only affected services;
5. an intentionally unhealthy revision triggers NixOS/secret rollback;
6. the admin key remains authorized after full activation;
7. logs redact secret values;
8. backup and restore recover a seeded Actual dataset.

The physical Lenovo deployment is an acceptance test after CI/VM success, not a
substitute for automated tests.

## 13. Documentation deliverables

Implementation must update or add:

- root `README.md`: install, deploy, secret rotation, LAN URL, and rollback quick
  start;
- `application/README.md`: services, internal topology, versions, storage, and health;
- `docs/SECRETS.md`: concrete threat model, dotenv bootstrap, `sops-nix`, rotation,
  and recovery;
- `docs/APPLICATION_OPERATIONS.md`: status, logs, restart, upgrade, model management,
  and incident checks;
- `docs/BACKUP_AND_RESTORE.md`: exact backup, restore, and restore-test procedures;
- repository layout documentation for every new module and command.

Commands must use visible placeholders and must never include copied production
tokens or passwords.

## 14. Milestones

### Milestone 0: decisions and preflight

- Inventory Lenovo RAM, CPU, free disk, LAN CIDRs, hostname, IPv6 use, and intended
  client devices.
- Decide Caddy internal CA versus an existing private PKI.
- Decide dotenv bootstrap versus immediate `sops-nix` adoption.
- Decide whether the Discord bot image will be published to GHCR or built by Nix.
- Benchmark candidate small Ollama models and choose one explicitly.

Exit criteria: all placeholders required to enable production have reviewed values;
no credentials are added to Git.

### Milestone 1: multi-image Compose/Nix foundation

- Refactor the image inventory and loader.
- Replace nginx with an Actual-only stack.
- Add persistent directories, loopback binding, Caddy, LAN firewall rules, and tests.

Exit criteria: Actual works via trusted LAN HTTPS, direct port access is blocked, and
startup requires no registry access.

### Milestone 2: backup and deployment utility

- Implement backup/restore.
- Implement full and secret-only deployment flows.
- Add activation health checks and rollback tests.

Exit criteria: a broken disposable deployment automatically restores the previous
healthy generation and secret set.

### Milestone 3: Ollama and actual-ai

- Add Ollama, model initialization, and resource policy.
- Add actual-ai in dry-run mode.
- Validate classifications before permitting writes.

Exit criteria: measured physical-host performance is acceptable and Actual remains
responsive under inference load.

### Milestone 4: Discord bot

- Establish immutable bot artifact provenance.
- Add runtime configuration, health reporting, and integration tests.
- Validate bank and receipt workflows with non-production fixtures first.

Exit criteria: the bot survives restart/reconnect, reaches Actual internally, exposes
no LAN port, and leaks no credentials.

### Milestone 5: production handoff

- Run restore drill.
- Deploy with a pre-upgrade backup.
- Install the private CA on clients and validate secure-context behavior.
- Verify LAN allow/deny behavior, health, resource use, logs, and reboot recovery.
- Record the deployed versions/digests and the rollback generation.

Exit criteria: all services recover after a real host reboot, backups are recoverable,
and no application port is reachable outside the declared trusted LAN path.

## 15. Explicit stop conditions

Stop deployment and preserve the current working system if:

- no verified Actual backup exists before a migration-bearing upgrade;
- the trusted LAN CIDR, hostname, target host, or SSH identity is ambiguous;
- an image or source dependency is mutable or cannot be verified;
- a secret would enter Git, a command argument, a log, or the Nix store;
- health checks fail or rollback cannot identify a known-good generation;
- the selected Ollama model exceeds available storage or causes sustained OOM/swap;
- enabling the firewall rules would expose Actual, Ollama, actual-ai, or the bot beyond
  the intended LAN;
- a full deployment would remove the only working admin SSH key;
- unrelated local changes would be overwritten.

These conditions block production activation, not the creation of non-destructive
tests and scaffolding.
