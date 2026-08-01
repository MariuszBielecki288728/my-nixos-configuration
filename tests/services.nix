{
  lib,
  netdataPkgs,
  pkgs,
}:
let
  monitoringPkgs = netdataPkgs;
in
assert lib.versionAtLeast monitoringPkgs.netdata.version "2.9.0";
pkgs.testers.runNixOSTest {
  name = "mini-pc-services";
  nodes.machine = {
    imports = [
      ../modules/users.nix
      ../modules/ssh.nix
      ../modules/docker.nix
      ../modules/application.nix
      ../modules/device-monitoring.nix
      ../modules/security.nix
    ];
    my.actualStack = {
      enable = true;
      hostname = "actual.test";
      trustedLanCidrs = [ "192.168.1.0/24" ];
    };
    my.deviceMonitoring = {
      enable = true;
      hostname = "actual.test";
      trustedLanCidrs = [ "192.168.1.0/24" ];
      retentionDays = 1;
      storageSizeMiB = 256;
      httpsPort = 8443;
      package = monitoringPkgs.netdata;
    };
    virtualisation.memorySize = 2048;
    virtualisation.diskSize = 6144;
    virtualisation.cores = 2;
    system.stateVersion = "25.11";
  };
  nodes.client = {
    environment.systemPackages = [ pkgs.curl ];
    system.stateVersion = "25.11";
  };
  testScript = ''

    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("sshd.service")
    machine.succeed("sshd -T | grep -qx 'passwordauthentication no'")
    machine.succeed("sshd -T | grep -qx 'kbdinteractiveauthentication no'")
    machine.succeed("sshd -T | grep -qx 'permitrootlogin no'")
    machine.wait_for_unit("docker.service")
    machine.wait_for_unit("mini-pc-image.service")
    machine.succeed("docker image inspect docker.io/actualbudget/actual-server:pinned-1449173e2221")
    machine.wait_for_unit("mini-pc-application.service", timeout=300)
    machine.wait_for_unit("caddy.service", timeout=300)
    machine.wait_for_unit("netdata.service", timeout=300)
    client.wait_for_unit("multi-user.target")
    client.wait_until_succeeds("getent ahostsv4 machine", timeout=60)
    machine.succeed("curl --fail --silent --output /dev/null http://127.0.0.1:5006/health")
    machine.succeed("test -s /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt")
    machine.succeed("curl --fail --silent --output /dev/null --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:443:127.0.0.1 https://actual.test/health")
    machine.succeed("curl --fail --silent --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:443:127.0.0.1 -D /tmp/actual-headers -o /dev/null https://actual.test/; cat /tmp/actual-headers; test $(grep -ic '^cross-origin-opener-policy:' /tmp/actual-headers) -eq 1; test $(grep -ic '^cross-origin-embedder-policy:' /tmp/actual-headers) -eq 1")
    machine.succeed("mini-pc-application-health")
    machine.succeed("mini-pc-monitoring-health")
    machine.succeed("curl --fail --silent --output /dev/null http://127.0.0.1:19999/api/v1/info")
    machine.succeed("curl --fail --silent --output /dev/null 'http://127.0.0.1:19999/api/v1/data?chart=system.cpu&after=-10'")
    machine.succeed("curl --fail --silent --output /dev/null --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:8443:127.0.0.1 https://actual.test:8443/api/v1/info")
    machine.succeed("curl --fail --silent --output /dev/null --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:8443:127.0.0.1 https://actual.test:8443/")
    machine.succeed("test $(curl --silent --output /dev/null --write-out '%{http_code}' --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:443:127.0.0.1 https://actual.test/status) = 308")
    machine.succeed("curl --silent --head --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:443:127.0.0.1 https://actual.test/status | grep -qi '^location: https://actual.test:8443/'")
    machine.succeed("test $(curl --silent --output /dev/null --write-out '%{http_code}' --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:443:127.0.0.1 https://actual.test/status/) = 308")
    machine.succeed("curl --silent --head --cacert /var/lib/mini-pc/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve actual.test:443:127.0.0.1 https://actual.test/status/ | grep -qi '^location: https://actual.test:8443/'")
    machine.succeed("test -f /etc/netdata/conf.d/.opt-out-from-anonymous-statistics")
    machine.succeed("systemctl show netdata --property=Environment --value | grep -q 'DO_NOT_TRACK=1'")
    machine.fail("id -nG mini-pc-monitoring | grep -qw docker")
    machine.fail("journalctl -u netdata --no-pager | grep -q '/var/run/docker.sock'")
    machine.fail("journalctl -u netdata --no-pager | grep -q 'debugfs.plugin'")
    client.succeed("address=$(getent ahostsv4 machine | awk 'NR == 1 { print $1 }'); curl --fail --insecure --silent --output /dev/null --resolve actual.test:443:$address https://actual.test/health")
    client.succeed("address=$(getent ahostsv4 machine | awk 'NR == 1 { print $1 }'); curl --fail --insecure --silent --output /dev/null --resolve actual.test:8443:$address https://actual.test:8443/api/v1/info")
    machine.succeed("device=$(ip -4 route show 192.168.1.0/24 | awk 'NR == 1 { print $3 }'); ip address add 198.51.100.1/24 dev \"$device\"")
    client.succeed("device=$(ip -4 route show 192.168.1.0/24 | awk 'NR == 1 { print $3 }'); ip address add 198.51.100.2/24 dev \"$device\"; ! curl --fail --insecure --silent --connect-timeout 2 --interface 198.51.100.2 --resolve actual.test:443:198.51.100.1 https://actual.test/health; ! curl --fail --insecure --silent --connect-timeout 2 --interface 198.51.100.2 --resolve actual.test:8443:198.51.100.1 https://actual.test:8443/api/v1/info")
    machine.succeed("ss -lnt | grep -q '127.0.0.1:5006'")
    machine.fail("ss -lnt | grep -Eq '(^|[[:space:]])(0.0.0.0|\\[::\\]):(5006|11434|19999)([[:space:]]|$)'")
    machine.succeed("ss -lnt | grep -q '127.0.0.1:19999'")
    machine.succeed("address=$(ip -4 -brief address show scope global | awk 'NR == 1 { sub(/\\/.*/, \"\", $3); print $3 }'); test -n \"$address\"; ! curl --fail --silent --max-time 2 \"http://$address:5006/health\"")
    machine.succeed("address=$(ip -4 -brief address show scope global | awk 'NR == 1 { sub(/\\/.*/, \"\", $3); print $3 }'); test -n \"$address\"; ! curl --fail --silent --max-time 2 \"http://$address:19999/api/v1/info\"")
    machine.succeed("nft list ruleset | grep -q 'ip saddr 192.168.1.0/24 tcp dport 8443 accept'")
    machine.succeed("nft list ruleset | grep -q 'ip saddr 192.168.1.0/24 tcp dport 443 accept'")
    machine.succeed("test $(stat -c %a /var/lib/mini-pc/secrets) = 700")
    machine.succeed("test $(stat -c %a /var/lib/mini-pc/backups/actual) = 700")
    machine.succeed("test -z \"$(find /nix/store -type f \\( -name 'discord-bot.env' -o -name 'compose.env' \\) -print -quit)\"")
    machine.succeed("touch /var/lib/mini-pc/actual/data/persistence-sentinel")
    machine.succeed("systemctl restart mini-pc-application.service")
    machine.succeed("test -f /var/lib/mini-pc/actual/data/persistence-sentinel")
    machine.succeed("systemctl start mini-pc-actual-backup.service")
    machine.succeed("find /var/lib/mini-pc/backups/actual -type f -name 'actual-*.tar.gz' -size +0 -print -quit | grep -q .")
    machine.wait_until_succeeds("mini-pc-application-health", timeout=120)
    machine.succeed("archive=$(find /var/lib/mini-pc/backups/actual -type f -name 'actual-*.tar.gz' -print -quit); rm /var/lib/mini-pc/actual/data/persistence-sentinel; printf '%s\\n' \"$archive\" | mini-pc-actual-restore \"$archive\"")
    machine.succeed("test -f /var/lib/mini-pc/actual/data/persistence-sentinel")
    machine.wait_until_succeeds("mini-pc-application-health", timeout=120)
  '';
}
