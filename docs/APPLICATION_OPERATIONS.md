# Application operations

## Production configuration

The generic profile leaves `my.actualStack.enable = false`. An enabled host must use a
reviewed hostname and trusted source CIDRs:

```nix
my.actualStack = {
  enable = true;
  hostname = "REPLACE_WITH_LAN_HOSTNAME";
  trustedLanCidrs = [ "REPLACE_WITH_REVIEWED_LAN_CIDR" ];
  discordBot.enable = false;
};
```

Actual binds to `127.0.0.1:5006`; only Caddy accepts LAN traffic on TCP 443. Do not add
router forwarding, UPnP, or a public tunnel. Enable the Discord bot only after its
least-privilege account, runtime secret contract, and channel access have been tested.

## Client CA trust

Caddy creates its private root certificate at:

```text
/var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt
```

Obtain and verify its SHA-256 fingerprint over authenticated SSH before installing it
in a client trust store:

```bash
ssh -i ~/.ssh/mini_pc_provision_ed25519 admin@think-centre.home \
  'sudo sha256sum /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt'

ssh -i ~/.ssh/mini_pc_provision_ed25519 admin@think-centre.home \
  'sudo install -m 0644 /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt /tmp/caddy-root.crt'

scp -i ~/.ssh/mini_pc_provision_ed25519 \
  admin@think-centre.home:/tmp/caddy-root.crt ./think-centre-caddy-root.crt
ssh -i ~/.ssh/mini_pc_provision_ed25519 admin@think-centre.home \
  'sudo rm /tmp/caddy-root.crt'
sha256sum ./think-centre-caddy-root.crt
```

Because the source file is root-readable, create the temporary copy explicitly over
SSH, set it world-readable only for the transfer, and remove it immediately afterward.
Do not copy Caddy's private CA key. Firefox may use its own certificate store depending
on platform policy; import only the verified root certificate as a trusted authority.

## Full NixOS and application deployment

Use the same command for configuration, service, image, and monitoring updates:

```bash
nix run .#deploy -- \
  --target admin@think-centre.home \
  --host m710q \
  --identity ~/.ssh/mini_pc_provision_ed25519 \
  --admin-key-file ~/.ssh/mini_pc_provision_ed25519.pub
```

Add `--application-env-file secrets/compose.env` only when installing or rotating the
optional application's validated secret contract. The full flow:

1. validates the target, admin public key, and optional secret file locally;
2. verifies SSH, sudo, architecture resources, and current application health;
3. builds a temporary key-preserving host configuration without editing tracked files;
4. copies the closure and immutable container archives through authenticated remote sudo;
5. prints the current and candidate generations and asks for the exact SSH target;
6. creates a consistent Actual backup and atomically stages optional secrets;
7. activates the candidate and runs application and monitoring health helpers;
8. on failure, records diagnostics and restores the prior generation and secret files.

The target does not need registry access. `nix copy --no-check-sigs` applies only to
the authenticated transfer into the target's root Nix store and does not weaken its
global signature policy. Deployment never prunes old generations or images.

After success, verify from the operator machine and target:

```bash
curl --fail https://think-centre.home/health
curl --fail https://think-centre.home:8443/api/v1/info

ssh -i ~/.ssh/mini_pc_provision_ed25519 admin@think-centre.home
sudo mini-pc-application-health
sudo mini-pc-monitoring-health
systemctl --no-pager --full status \
  mini-pc-application mini-pc-discord-bot caddy netdata
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

The monitoring commands apply only when `my.deviceMonitoring` is enabled. Follow
[monitoring operations](MONITORING.md) for the browser URL and sensor checks.

## Updating pinned software

An update is a reviewed repository change, not a runtime pull:

1. update the Nix input or application image version, manifest digest, linux/amd64
   content digest, and Nix fixed-output hash together;
2. review release notes, database migrations, architecture, and security impact;
3. run the checks in [testing and CI](TESTING.md), including the service VM;
4. ensure a current Actual backup exists and perform a restore drill for a risky migration;
5. merge only after CI succeeds, then deploy with the full command above;
6. retain the old generation and backup until the update has been observed as healthy.

Never use `latest`, a floating branch, `pull_policy: always`, or an automatic production
activation. A database migration may require restoring data as well as reverting the
container generation.

## Secret-only rotation

Create or update the ignored mode-0600 file as documented in [secrets](SECRETS.md), then:

```bash
nix run .#deploy -- \
  --target admin@think-centre.home \
  --identity ~/.ssh/mini_pc_provision_ed25519 \
  --secrets-only \
  --application-env-file secrets/compose.env
```

Do not pass `--host` or `--admin-key-file` in secret-only mode. The command validates
and atomically replaces the root-owned service file, restarts only an enabled consumer,
checks health, and restores the previous file if health fails.

## Rollback

Deployment performs automatic rollback when candidate health fails. For a later manual
rollback, first identify the validated prior generation:

```bash
readlink -f /run/current-system
sudo nix-env --list-generations --profile /nix/var/nix/profiles/system
```

Prefer selecting the prior generation from the systemd-boot menu. For attended remote
recovery, activate the exact reviewed store path and immediately rerun health checks:

```bash
sudo /nix/store/REVIEWED_NIXOS_SYSTEM_PATH/bin/switch-to-configuration switch
sudo mini-pc-application-health
sudo mini-pc-monitoring-health
```

Never delete the current or previous generation during an incident. If a database
migration is incompatible, follow [backup and restore](BACKUP_AND_RESTORE.md).

## Routine operation and incidents

```bash
sudo mini-pc-application-health
systemctl is-active docker mini-pc-application caddy
systemctl list-timers mini-pc-actual-backup.timer
sudo journalctl -u mini-pc-application -u caddy --since today
sudo docker logs --tail 200 mini-pc-actual-actual-server-1
sudo docker logs --tail 200 mini-pc-actual-actual-discord-bot-1
df -h / /var/lib/mini-pc
```

The Discord bot has a separate unit and cannot take Actual down. Restart the narrowest
failed boundary first; do not use `docker compose down -v`, delete application data,
prune images, or remove generations as a troubleshooting shortcut.

For a direct-cable installation, complete installed-system verification before moving
the target to its normal network. An unknown Windows adapter state is not authorization
to enable application CIDRs or temporary DHCP on a LAN.
