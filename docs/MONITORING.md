# Device monitoring operations

## Overview

The M710q profile enables a local-only Netdata Agent and publishes its bundled
dashboard through a dedicated Caddy HTTPS origin:

```text
browser -> HTTPS think-centre.home:8443/ -> Caddy
                                               |
                                               v
                                       127.0.0.1:19999
                                               |
                                               v
                               Netdata collector and local dbengine
```

Netdata is pinned by `flake.lock` through Nixpkgs. It is not installed by an
upstream shell script, does not self-update, is not claimed to Netdata Cloud, and
has anonymous analytics disabled. The `pkgs.netdataCloud` variant name refers to the
locally bundled dashboard, not a claimed Agent or a Cloud service. Its reviewed UI
archive is fixed-output and pinned by Nixpkgs; opening the dashboard does not need
Cloud-hosted dashboard assets or an account. The bundled UI uses Netdata's
redistributable NCUL1 license, so the module's unfree predicate is limited to the
`netdata` package name.

Because NCUL1 is classified as unfree by Nixpkgs, an enabling host must add the
narrow predicate used by `hosts/m710q/default.nix`; the reusable module does not
globally change a caller's package policy:

```nix
nixpkgs.config.allowUnfreePredicate = package: lib.getName package == "netdata";
```

The reusable interface is `my.deviceMonitoring` in
`modules/device-monitoring.nix`:

```nix
my.deviceMonitoring = {
  enable = true;
  hostname = "REPLACE_WITH_LAN_HOSTNAME";
  trustedLanCidrs = [ "REPLACE_WITH_REVIEWED_LAN_CIDR" ];
  listenAddress = "127.0.0.1";
  port = 19999;
  pathPrefix = "/status";
  httpsPort = 8443;
  updateEverySeconds = 2;
  retentionDays = 14;
  storageSizeMiB = 512;
  package = pkgs.netdataCloud;
};
```

The module deliberately accepts only `127.0.0.1` for the backend. Caddy is
the only LAN-facing listener, and the firewall permits dashboard HTTPS on TCP 8443
only from the reviewed CIDRs.
The Netdata service uses the dedicated `mini-pc-monitoring` account rather than the
default account that the upstream NixOS module would add to the root-equivalent
Docker group. Docker socket discovery is explicitly disabled. The go.d collector
defaults to off and only its sensors module
is enabled. Unneeded Python, process, cgroup, IPMI, performance, journal, network
viewer, OpenTelemetry, and privileged debugfs plugins are also disabled. The
unprivileged go.d sensor collector avoids duplicate temperature charts while CPU
frequency remains available from Netdata's standard proc collectors.

Netdata 2.8 service discovery ignores symlinked configuration entries, while the
upstream NixOS `services.netdata.configDir` option creates a symlink tree. The
module therefore points go.d at a generated Nix store directory containing regular
files. This is intentional: it makes the Docker service-discovery opt-out effective
and is covered by a journal assertion in the service VM test.

## Physical sensor discovery

Read-only discovery on the Lenovo ThinkCentre M710q on 2026-07-31 confirmed these
capabilities without storing a machine-specific hardware report:

- `coretemp` exposes CPU package temperature and both CPU core temperatures;
- the NVMe `hwmon` device exposes its composite and sensor temperatures;
- both logical CPUs expose `scaling_cur_freq`;
- the deployed image did not previously include the `sensors` command.

The monitoring module now installs `lm_sensors` for operator diagnostics. Repeat
discovery after kernel or hardware changes:

```bash
find -L /sys/class/hwmon -maxdepth 2 -type f -name 'temp*_input' -print
find /sys/devices/system/cpu -path '*/cpufreq/scaling_cur_freq' -print
sensors -j
```

The `-L` is important because `/sys/class/hwmon/hwmon*` entries are symlinks.
Sensor labels and paths may change across kernels; the module contains no hard-coded
sensor name or path.

## Physical acceptance

The rollback-capable deployment completed on the M710q on 2026-07-31. The first
candidate activation encountered a transient monitoring health-check race and was
automatically returned to the prior generation. Bounded connection retries were
then added to `mini-pc-monitoring-health`; the subsequent activation passed without
pruning any generation.

Post-activation checks confirmed:

- application, Discord bot, Caddy, and Netdata units are active and both repository
  health commands pass;
- the Netdata backend listens only on `127.0.0.1:19999`, while Caddy serves the
  dashboard on HTTPS port 8443;
- six unprivileged temperature charts cover three CPU package/core sensors and
  three NVMe sensors, and `cpu.cpufreq` reports both logical CPUs;
- temperature and frequency history returned 15 samples for a 30-second query at
  the configured two-second interval;
- the current Netdata process did not start `debugfs.plugin`, did not attempt the
  Docker socket, and the monitoring user belongs only to its dedicated group;
- the initial database footprint was approximately 11 MiB in `/var/cache/netdata`
  and 48 KiB in `/var/lib/netdata`. This is only a baseline; review growth after a
  full retention window.

The same HTTPS checks returned the bundled Netdata page and local API on port 8443,
plus the Actual root and Actual health endpoint on port 443, successfully from the
development machine.

Firefox acceptance on 2026-08-01 exposed a collision in the original `/status/`
design: Actual's root-scoped service worker handled that navigation as an application
route and opened `/budget` without sending the request to Caddy. The dashboard was
therefore moved to the separate `https://think-centre.home:8443/` origin and deployed
with rollback protection. Follow-up checks confirmed HTTP 200 responses from the
dashboard and API on port 8443, HTTP 308 redirects from both legacy path forms for
non-service-worker clients, healthy Actual endpoints on port 443, and passing
application and monitoring health commands on the physical host.

## Retention and storage

The base host collectors and sensor job use the configured two-second interval. The
default database has one tier. Netdata removes data when either the 14-day time
limit or the 512 MiB soft size target is reached. The size is a retention target
rather than a strict filesystem quota and can be temporarily exceeded. History is
operational data and is not included in the Actual backup workflow.

Inspect actual growth after deployment:

```bash
sudo du -sh /var/cache/netdata /var/lib/netdata
sudo journalctl -u netdata --since today
```

Change retention only through `my.deviceMonitoring`, deploy a new generation, and
then confirm the effective values in `/etc/netdata/netdata.conf` and the dashboard's
dbengine retention charts.

## Using the status page

Open the complete URL, including the port:

```text
https://think-centre.home:8443/
```

Do not use `/status/` as the primary address. Actual registers a service worker for
the entire `https://think-centre.home` origin. In a browser that has opened Actual,
that worker can answer `/status/` with Actual's cached page before Caddy receives a
request, which leads to `/budget`. TCP 8443 is a distinct browser origin and is not
controlled by that worker. The legacy `/status` and `/status/` routes redirect to the
port for clients whose navigation is not already intercepted.

Clients must resolve the LAN hostname and trust Caddy's local root CA. Follow the CA
installation procedure in `docs/APPLICATION_OPERATIONS.md` if Firefox displays an
unknown-issuer warning. Bookmark the port-qualified URL after it opens successfully.
Clearing Firefox site data or unregistering Actual's worker is not required for the
new URL. It is useful only if testing the legacy redirect.

The landing page shows live host charts. Use the dashboard's chart search to find:

- `CPU Frequency` for both logical CPUs;
- `Sensor Temperature` for CPU package, CPU cores, and NVMe sensors;
- CPU utilization, load, memory, filesystem, disk I/O, and network charts from the
  standard host collectors.

Use a chart's time controls to move from live values to recent history, and drag over
a chart to inspect a shorter interval. The configured history window is at most 14
days and 512 MiB; the older boundary may be shorter until enough data has accumulated.
Refresh the port-qualified URL directly when troubleshooting a nested dashboard view.

The dashboard has no application login: access control is the LAN-only
nftables source policy. Monitoring data is sensitive, and no router port forwarding
should expose TCP 8443 publicly.

## Health checks and troubleshooting

Useful checks on the host are:

```bash
sudo mini-pc-monitoring-health
systemctl status netdata caddy
ss -lnt | grep 19999
curl --fail http://127.0.0.1:19999/api/v1/info
sudo curl --fail --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt \
  https://think-centre.home:8443/api/v1/info
sensors
```

`mini-pc-monitoring-health` verifies the service, loopback API, bundled UI, and both
resources through HTTPS port 8443. Full repository deployment calls this command and
restores the prior NixOS generation if it fails.

If Firefox still opens `/budget`, check the address bar first: it must contain
`:8443` and no `/status` suffix. Then verify from the host:

```bash
sudo mini-pc-monitoring-health
sudo ss -lnt | grep ':8443'
```

If these pass but Firefox cannot connect, confirm that the client is within the
configured trusted LAN CIDR and that no proxy, VPN, or DNS-over-HTTPS policy sends the
local hostname elsewhere.

## Deploy, update, and roll back

Use the normal installed-host deployment path; it builds from pinned inputs, copies
the closure over authenticated SSH, activates only after confirmation, and retains
the prior generation:

```bash
nix run .#deploy -- \
  --target admin@think-centre.home \
  --host m710q \
  --identity ~/.ssh/mini_pc_provision_ed25519 \
  --admin-key-file ~/.ssh/mini_pc_provision_ed25519.pub
```

Type the complete target when prompted. A failed health check switches back
automatically. For an operator-initiated rollback, select the previous system from
the boot menu or activate its validated `/nix/store/...-nixos-system-...` path with
`switch-to-configuration switch`, then rerun both application and monitoring health
commands.

To remove the dashboard, set `my.deviceMonitoring.enable = false` and deploy. That
stops serving TCP 8443 and the legacy redirect, and disables Netdata, but deliberately
does not erase metric history. After verifying the rollback, the exact Netdata state
and cache directories may be removed manually only if losing all monitoring history
is intended.

## Test coverage and current limits

`tests/services.nix` proves service startup, loopback-only binding, lack of Docker
group membership, analytics opt-out, recent historical data, bundled UI and API on
the isolated HTTPS port, the legacy redirect, and rejection of direct backend access
over the VM LAN. The test also keeps the existing Actual root route and source
firewall checks.

A VM cannot prove physical sensor availability. Container names and detailed Docker
health are outside monitoring because the agent is not granted Docker socket access.
Netdata can still report generic cgroup activity; application health continues to be
checked by `mini-pc-application-health`. Automated checks fetch the bundled page and
live API but do not execute browser JavaScript; interactive navigation and refresh
remain a manual client acceptance check.
