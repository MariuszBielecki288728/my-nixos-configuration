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
443, Caddy proxies to `127.0.0.1:5006`, and Ollama has no host port. Install Caddy's
root certificate from
`/var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt` in each
client trust store after verifying its fingerprint over SSH.

AI remains disabled until the configured Ollama model is tested on the Pentium
G4400T for download size, free disk, peak RAM, inference latency, and sustained CPU.
Enable `actualAi.enable` only with an explicit model name and keep actual-ai in
`dryRun` until classifications are reviewed. Enable `discordBot.enable` only after
creating a least-privilege Discord bot and testing login/channel access.

### Physical M710q Ollama benchmark

The first physical target was measured on 2026-07-19. It has a two-core/two-thread
Pentium G4400T at 2.9 GHz, 8.2 GB RAM, no swap, and a 128 GB NVMe with 114.7 GB
available before the test. The CPU exposes neither AVX nor AVX2, so Ollama selected
its generic `cpu` backend. The Intel display device was not passed to the container;
the benchmark was deliberately CPU-only, matching the deployed design.

The repository-pinned Ollama 0.32.1 image ran with two CPUs, a 3 GB memory limit, one
loaded model, a 2,048-token context, and deterministic decoding. Six synthetic Polish
merchant titles were classified against ten named categories with UUID identifiers.
These are smoke-test results, not a substitute for a representative labelled export.

| Model | Download | Resident container memory | Latency | Exact result |
| --- | ---: | ---: | ---: | ---: |
| `qwen2.5:0.5b` | 398 MB | 491 MiB | 66 s cold; 13.3-14.5 s warm | 0/6 |
| `gemma3:270m` | 292 MB | 384 MiB | 9.6 s cold; 7.5-7.7 s warm | 0/6 |
| `gemma3:1b` | 815 MB | about 999 MiB | 114-131 s per title | 0/1 |

All models fit in memory, but inference saturated both cores. The two fast models
collapsed to an invalid constant or the first category. The 1B model was both wrong
and too slow for per-transaction use. An exact `actual-ai`-style JSON request also
returned code-fenced, invalid JSON. In addition, `actual-ai` 2.4.2's Ollama fallback
checks that a response contains a UUID but then treats the complete response as the
category ID, while its default prompt asks for a JSON object.

Do not enable `actualAi` with these models on this host. Prefer deterministic Actual
rules for recurring merchants, a remote model endpoint, or a purpose-built small
classifier trained and evaluated on labelled transactions. Any future Ollama retest
must use a corrected Ollama response parser, a representative private test set, an
explicit accuracy threshold, and a schedule that cannot contend with backups or
interactive Actual use.

## Deployment

Full deployments build on the development PC and require no target registry access:

```bash
nix run .#deploy -- \
  --target admin@HOST \
  --host m710q \
  --identity ~/.ssh/id_ed25519 \
  --application-env-file secrets/compose.env
```

The command verifies SSH/sudo, architecture, disk space, and current health; builds
and copies the closure; loads images; prints the change summary; backs up Actual;
stages secrets atomically; activates; and verifies. On failure it collects service
and container diagnostics and restores both the previous generation and secret files.
Type the complete target when prompted. `--yes` is limited to disposable localhost CI.

Useful checks on the target are:

```bash
sudo mini-pc-application-health
sudo systemctl status mini-pc-application caddy
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

Use `journalctl -u UNIT` for native units and `docker logs CONTAINER` for a container.
Image/model failures do not take Actual down: Ollama, model initialization, actual-ai,
and Discord use separate units. There is no automatic image prune.

## Direct-cable note

A directly connected PC and mini-PC have no router DHCP service. Use the repository's
reviewed provisioning network for rescue/install, then configure and verify the real
installed-host address before enabling a CIDR. Physical activation is intentionally
not automated from an unknown Windows adapter state.
