# Application operations

## Production activation

The generic and M710q profiles keep `my.actualStack.enable = false` by default. Before
enabling it in the selected host, discover the real directly connected/LAN subnet and
choose a stable hostname. Do not copy the VM values. A minimal reviewed override is:

```nix
my.actualStack = {
  enable = true;
  hostname = "REPLACE_WITH_LAN_HOSTNAME";
  trustedLanCidrs = [ "REPLACE_WITH_REVIEWED_LAN_CIDR" ];
};
```

Do not add router port forwarding. The firewall permits only declared source CIDRs on
443, and Caddy proxies to `127.0.0.1:5006`. Install Caddy's root certificate from
`/var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt` in each
client trust store after verifying its fingerprint over SSH.

Enable `discordBot.enable` only after creating a least-privilege Discord bot and
testing login and channel access.

## Deployment

Full deployments build on the development PC and require no target registry access:

```bash
nix run .#deploy -- \
  --target admin@HOST \
  --host m710q \
  --identity ~/.ssh/id_ed25519
```

The command verifies SSH/sudo, architecture, disk space, and current health; builds
and copies the closure through the target's passwordless `sudo nix-store` boundary;
loads images; prints the change summary; backs up Actual; optionally stages a supplied
secret file atomically; activates; and verifies. The authenticated transfer permits
the unsigned locally built closure only for that copy operation and does not weaken
the target's global signature policy. On failure it collects service and container
diagnostics and restores both the previous generation and any changed secret file.
Type the complete target when prompted. `--yes` is limited to disposable localhost CI.

Useful checks on the target are:

```bash
sudo mini-pc-application-health
sudo systemctl status mini-pc-application caddy
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Use `journalctl -u UNIT` for native units and `docker logs CONTAINER` for a container.
Discord failures do not take Actual down because the bot uses a separate unit. There
is no automatic image prune.

## Direct-cable note

A directly connected PC and mini-PC have no router DHCP service. Use the repository's
reviewed provisioning network for rescue/install, then configure and verify the real
installed-host address before enabling a CIDR. Physical activation is intentionally
not automated from an unknown Windows adapter state.
