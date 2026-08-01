{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.my.deviceMonitoring;
  inherit (lib)
    concatStringsSep
    hasInfix
    mkEnableOption
    mkIf
    mkOption
    optional
    types
    ;

  placeholder = value: hasInfix "REPLACE_WITH_" value;
  validCidr = value: builtins.match "^[0-9A-Fa-f:.]+/[0-9]{1,3}$" value != null;
  validPath = builtins.match "^/[A-Za-z0-9][A-Za-z0-9/_-]*$" cfg.pathPrefix != null;
  ipv4Cidrs = builtins.filter (cidr: !hasInfix ":" cidr) cfg.trustedLanCidrs;
  ipv6Cidrs = builtins.filter (cidr: hasInfix ":" cidr) cfg.trustedLanCidrs;
  sourceRules =
    optional (ipv4Cidrs != [ ]) (
      "ip saddr { ${concatStringsSep ", " ipv4Cidrs} } tcp dport ${toString cfg.httpsPort} accept comment \"Monitoring trusted IPv4 LAN\""
    )
    ++ optional (ipv6Cidrs != [ ]) (
      "ip6 saddr { ${concatStringsSep ", " ipv6Cidrs} } tcp dport ${toString cfg.httpsPort} accept comment \"Monitoring trusted IPv6 LAN\""
    );

  backend = "${cfg.listenAddress}:${toString cfg.port}";
  goConfig = pkgs.runCommand "mini-pc-netdata-go-config" { } ''
    mkdir -p "$out/go.d/sd"
    cp ${pkgs.writeText "go.d.conf" ''
      enabled: yes
      default_run: no
      modules:
        sensors: yes
    ''} "$out/go.d.conf"
    cp ${pkgs.writeText "docker-disabled.conf" ''
      disabled: yes
    ''} "$out/go.d/sd/docker.conf"
    cp ${pkgs.writeText "sensors.conf" ''
      jobs:
        - name: sensors
          update_every: ${toString cfg.updateEverySeconds}
          binary_path: ${lib.getExe pkgs.lm_sensors}
    ''} "$out/go.d/sensors.conf"
  '';
  health = pkgs.writeShellApplication {
    name = "mini-pc-monitoring-health";
    runtimeInputs = with pkgs; [
      coreutils
      curl
      systemd
    ];
    text = ''
      systemctl is-active --quiet netdata caddy
      curl_flags=(
        --fail
        --silent
        --show-error
        --max-time 10
        --retry 10
        --retry-connrefused
        --retry-delay 1
      )
      curl "''${curl_flags[@]}" \
        --noproxy '*' \
        --output /dev/null \
        http://${backend}/api/v1/info
      curl "''${curl_flags[@]}" \
        --noproxy '*' \
        --output /dev/null \
        http://${backend}/
      ca=${config.services.caddy.dataDir}/.local/share/caddy/pki/authorities/local/root.crt
      test -s "$ca"
      curl "''${curl_flags[@]}" \
        --noproxy '*' \
        --cacert "$ca" \
        --resolve ${cfg.hostname}:${toString cfg.httpsPort}:127.0.0.1 \
        --output /dev/null \
        https://${cfg.hostname}:${toString cfg.httpsPort}/api/v1/info
      curl "''${curl_flags[@]}" \
        --noproxy '*' \
        --cacert "$ca" \
        --resolve ${cfg.hostname}:${toString cfg.httpsPort}:127.0.0.1 \
        --output /dev/null \
        https://${cfg.hostname}:${toString cfg.httpsPort}/
    '';
  };
in
{
  options.my.deviceMonitoring = {
    enable = mkEnableOption "LAN-only local device monitoring dashboard";
    hostname = mkOption {
      type = types.str;
      default = "REPLACE_WITH_LAN_HOSTNAME";
      description = "Reviewed LAN hostname whose Caddy site receives the dashboard route";
    };
    trustedLanCidrs = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Reviewed IPv4 and IPv6 source CIDRs allowed to reach Caddy HTTPS";
    };
    listenAddress = mkOption {
      type = types.str;
      default = "127.0.0.1";
      description = "Loopback address on which the Netdata backend listens";
    };
    port = mkOption {
      type = types.port;
      default = 19999;
      description = "Loopback-only Netdata backend port";
    };
    pathPrefix = mkOption {
      type = types.str;
      default = "/status";
      description = "Caddy path prefix without a trailing slash";
    };
    httpsPort = mkOption {
      type = types.port;
      default = 8443;
      description = "LAN-facing Caddy HTTPS port, isolated from root-scoped service workers";
    };
    updateEverySeconds = mkOption {
      type = types.ints.positive;
      default = 2;
      description = "Base host metric collection interval";
    };
    retentionDays = mkOption {
      type = types.ints.positive;
      default = 14;
      description = "Maximum wall-clock retention for the single local metrics tier";
    };
    storageSizeMiB = mkOption {
      type = types.ints.positive;
      default = 512;
      description = "Soft disk-space ceiling for the single local metrics tier";
    };
    package = mkOption {
      type = types.package;
      default = pkgs.netdataCloud;
      defaultText = lib.literalExpression "pkgs.netdataCloud";
      description = "Pinned Netdata package variant with its dashboard bundled locally";
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion =
          !placeholder cfg.hostname && builtins.match "^[A-Za-z0-9][A-Za-z0-9.-]*$" cfg.hostname != null;
        message = "my.deviceMonitoring.hostname must be a reviewed LAN hostname";
      }
      {
        assertion = cfg.trustedLanCidrs != [ ] && builtins.all validCidr cfg.trustedLanCidrs;
        message = "my.deviceMonitoring.trustedLanCidrs must contain reviewed IPv4/IPv6 CIDRs";
      }
      {
        assertion = cfg.listenAddress == "127.0.0.1";
        message = "device monitoring permits only the IPv4 loopback listen address";
      }
      {
        assertion = validPath && !hasInfix "//" cfg.pathPrefix;
        message = "my.deviceMonitoring.pathPrefix must be a safe absolute path without a trailing slash";
      }
      {
        assertion = cfg.httpsPort != 443 && cfg.httpsPort != cfg.port;
        message = "my.deviceMonitoring.httpsPort must differ from HTTPS 443 and the Netdata backend port";
      }
      {
        assertion = cfg.storageSizeMiB >= 256;
        message = "Netdata enforces a minimum 256 MiB dbengine tier size";
      }
    ];

    environment.systemPackages = [
      health
      pkgs.lm_sensors
    ];

    users.groups.mini-pc-monitoring = { };
    users.users.mini-pc-monitoring = {
      isSystemUser = true;
      group = "mini-pc-monitoring";
      description = "Unprivileged local metrics collector";
    };

    services.netdata = {
      enable = true;
      package = cfg.package;
      user = "mini-pc-monitoring";
      group = "mini-pc-monitoring";
      enableAnalyticsReporting = false;
      claimTokenFile = null;
      python.enable = false;
      config = {
        global = {
          "bind socket to IP" = cfg.listenAddress;
          "config directory" = goConfig;
          "default port" = toString cfg.port;
          "update every" = toString cfg.updateEverySeconds;
        };
        db = {
          db = "dbengine";
          "storage tiers" = "1";
          "dbengine tier 0 retention time" = "${toString cfg.retentionDays}d";
          "dbengine tier 0 retention size" = "${toString cfg.storageSizeMiB}MiB";
        };
        plugins = {
          "apps" = "no";
          "charts.d" = "no";
          "cgroups" = "no";
          "debugfs" = "no";
          "freeipmi" = "no";
          "network-viewer" = "no";
          "otel" = "no";
          "perf" = "no";
          "python.d" = "no";
          "systemd-journal" = "no";
        };
      };
    };

    networking.nftables.enable = true;
    networking.firewall.extraInputRules = concatStringsSep "\n" sourceRules;

    services.caddy = {
      enable = true;
      virtualHosts = {
        ${cfg.hostname}.extraConfig = ''
          redir ${cfg.pathPrefix} https://${cfg.hostname}:${toString cfg.httpsPort}/ 308
          redir ${cfg.pathPrefix}/ https://${cfg.hostname}:${toString cfg.httpsPort}/ 308
        '';
        "https://${cfg.hostname}:${toString cfg.httpsPort}".extraConfig = ''
          tls internal
          reverse_proxy ${backend}
        '';
      };
    };
  };
}
