{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.my.actualStack;
  inherit (lib)
    concatMapStringsSep
    concatStringsSep
    filterAttrs
    hasInfix
    mapAttrs
    mkEnableOption
    mkIf
    mkOption
    optional
    types
    ;

  imageType = types.submodule {
    options = {
      imageName = mkOption {
        type = types.str;
        description = "Registry repository without a mutable tag";
      };
      sourceDigest = mkOption {
        type = types.str;
        description = "Pinned registry manifest digest fetched by dockerTools.pullImage";
      };
      contentDigest = mkOption {
        type = types.str;
        description = "Pinned linux/amd64 manifest digest used by Compose";
      };
      nixHash = mkOption {
        type = types.str;
        description = "Nix fixed-output hash of the normalized linux/amd64 archive";
      };
      version = mkOption {
        type = types.str;
        description = "Reviewed upstream version label for operator output";
      };
      archive = mkOption {
        type = types.nullOr types.package;
        default = null;
        description = "Optional prebuilt archive override used by disposable tests";
      };
    };
  };

  imageDefaults = {
    actual = {
      imageName = "docker.io/actualbudget/actual-server";
      sourceDigest = "sha256:1449173e2221eb9387da866723808a1fa32a3e92e5cca5df65dc90a532c81ac8";
      contentDigest = "sha256:2dff01a93343cae5020d3409f6c0b0be92363acb63343e8e5b67ad5c3f172268";
      nixHash = "sha256-uixGAnKKoSggH8JpBQDTu8MRjGQUm4bLHkMTwaW8+0E=";
      version = "26.7.0-alpine";
    };
    discordBot = {
      imageName = "ghcr.io/mariuszbielecki288728/actual-discord-bot";
      sourceDigest = "sha256:349b8d9ed77d1be0d28365562ce1b9f4469a4f5edf578924276b57a5b89d4bfb";
      contentDigest = "sha256:349b8d9ed77d1be0d28365562ce1b9f4469a4f5edf578924276b57a5b89d4bfb";
      nixHash = "sha256-vkPtgUVkJ0QSL43srVpnnLFAQh/+iDGAxw0nR7gm0vU=";
      # OCI revision: 8d987b24371e87de698581916d46ac2d45ad42d4.
      version = "v0.5.0";
    };
  };

  activeImageNames = [
    "actual"
  ]
  ++ optional cfg.discordBot.enable "discordBot";
  activeImages = filterAttrs (name: _image: builtins.elem name activeImageNames) cfg.images;
  loadedTag = image: "pinned-${builtins.substring 7 12 image.sourceDigest}";
  imageReference = image: "${image.imageName}:${loadedTag image}";
  imageArchive =
    image:
    if image.archive != null then
      image.archive
    else
      pkgs.dockerTools.pullImage {
        inherit (image) imageName;
        imageDigest = image.sourceDigest;
        hash = image.nixHash;
        finalImageName = image.imageName;
        finalImageTag = loadedTag image;
      };
  imageArchives = mapAttrs (_name: imageArchive) activeImages;
  digestPattern = "^sha256:[0-9a-f]{64}$";
  hashPattern = "^sha256-[A-Za-z0-9+/]{43}=$";
  placeholder = value: hasInfix "REPLACE_WITH_" value;
  validCidr = value: builtins.match "^[0-9A-Fa-f:.]+/[0-9]{1,3}$" value != null;
  ipv4Cidrs = builtins.filter (cidr: !hasInfix ":" cidr) cfg.trustedLanCidrs;
  ipv6Cidrs = builtins.filter (cidr: hasInfix ":" cidr) cfg.trustedLanCidrs;
  sourceRules =
    optional (ipv4Cidrs != [ ]) (
      "ip saddr { ${concatStringsSep ", " ipv4Cidrs} } tcp dport 443 accept comment \"Actual trusted IPv4 LAN\""
    )
    ++ optional (ipv6Cidrs != [ ]) (
      "ip6 saddr { ${concatStringsSep ", " ipv6Cidrs} } tcp dport 443 accept comment \"Actual trusted IPv6 LAN\""
    );
  composeFile = ../application/compose.yaml;
  composeCommand = "${pkgs.docker-compose}/bin/docker-compose -f ${composeFile}";
  composeEnvironment = {
    ACTUAL_IMAGE = imageReference cfg.images.actual;
    DISCORD_BOT_IMAGE = imageReference cfg.images.discordBot;
    ACTUAL_LOOPBACK_PORT = toString cfg.actualLoopbackPort;
  };
  composeEnvironmentExports = concatStringsSep "\n" (
    lib.mapAttrsToList (name: value: "export ${name}=${lib.escapeShellArg value}") composeEnvironment
  );
  loadImages = pkgs.writeShellApplication {
    name = "mini-pc-load-images";
    runtimeInputs = [ pkgs.docker_29 ];
    text = concatMapStringsSep "\n" (archive: "docker load < ${archive}") (
      builtins.attrValues imageArchives
    );
  };
  health = pkgs.writeShellApplication {
    name = "mini-pc-application-health";
    runtimeInputs = with pkgs; [
      coreutils
      curl
      gnugrep
      gnused
      systemd
    ];
    text = ''
      systemctl is-active --quiet docker mini-pc-application caddy
      curl --fail --silent --show-error --max-time 10 \
        --noproxy '*' \
        --output /dev/null \
        http://127.0.0.1:${toString cfg.actualLoopbackPort}/health
      ca=${cfg.dataRoot}/caddy/.local/share/caddy/pki/authorities/local/root.crt
      test -s "$ca"
      headers=$(mktemp)
      trap 'rm -f "$headers"' EXIT
      curl --fail --silent --show-error --max-time 10 \
        --noproxy '*' \
        --cacert "$ca" \
        --resolve ${cfg.hostname}:443:127.0.0.1 \
        --output /dev/null \
        https://${cfg.hostname}/health
      curl --fail --silent --show-error --max-time 10 \
        --noproxy '*' \
        --cacert "$ca" \
        --resolve ${cfg.hostname}:443:127.0.0.1 \
        --dump-header "$headers" \
        --output /dev/null \
        https://${cfg.hostname}/
      test "$(grep -ic '^cross-origin-opener-policy:' "$headers")" -eq 1
      test "$(grep -ic '^cross-origin-embedder-policy:' "$headers")" -eq 1
      ${lib.optionalString cfg.discordBot.enable ''
        systemctl is-active --quiet mini-pc-discord-bot
        docker inspect --format '{{.State.Health.Status}}' mini-pc-actual-actual-discord-bot-1 | grep -qx healthy
      ''}
    '';
  };
  backup = pkgs.writeShellApplication {
    name = "mini-pc-actual-backup";
    runtimeInputs = with pkgs; [
      coreutils
      docker-compose
      findutils
      gzip
      gnutar
      util-linux
    ];
    text = ''
      ${composeEnvironmentExports}
      backup_dir=${cfg.dataRoot}/backups/actual
      data_dir=${cfg.dataRoot}/actual/data
      mkdir -p "$backup_dir"
      exec 9>"$backup_dir/.backup.lock"
      flock -n 9 || { echo "another Actual backup is running" >&2; exit 1; }
      timestamp=$(date -u +%Y%m%dT%H%M%SZ)
      temporary="$backup_dir/.actual-$timestamp.tar.gz.tmp"
      archive="$backup_dir/actual-$timestamp.tar.gz"
      cleanup() {
        rm -f "$temporary"
        ${composeCommand} start actual-server >/dev/null 2>&1 || true
      }
      trap cleanup EXIT
      ${composeCommand} stop -t 30 actual-server
      tar --create --gzip --file "$temporary" --directory "$data_dir" .
      tar --list --gzip --file "$temporary" >/dev/null
      test -s "$temporary"
      mv "$temporary" "$archive"
      chmod 0600 "$archive"
      ${composeCommand} start actual-server
      find "$backup_dir" -maxdepth 1 -type f -name 'actual-*.tar.gz' \
        -mtime +${toString cfg.backupRetentionDays} -delete
      trap - EXIT
      printf '%s\n' "$archive"
    '';
  };
  restore = pkgs.writeShellApplication {
    name = "mini-pc-actual-restore";
    runtimeInputs = with pkgs; [
      coreutils
      docker-compose
      gzip
      gnutar
    ];
    text = ''
      ${composeEnvironmentExports}
      if [[ $# -ne 1 ]]; then
        echo "usage: mini-pc-actual-restore /absolute/path/to/actual-TIMESTAMP.tar.gz" >&2
        exit 2
      fi
      archive=$1
      [[ "$archive" = /* && -f "$archive" ]] || { echo "backup must be an existing absolute path" >&2; exit 2; }
      tar --list --gzip --file "$archive" >/dev/null
      read -r -p "Type the full backup path to replace Actual data: " confirmation
      [[ "$confirmation" == "$archive" ]] || { echo "confirmation did not match" >&2; exit 1; }
      data_dir=${cfg.dataRoot}/actual/data
      rollback=${cfg.dataRoot}/actual/.restore-rollback
      staged=${cfg.dataRoot}/actual/.restore-staged
      rm -rf -- "$rollback" "$staged"
      mkdir -p "$staged"
      tar --extract --gzip --file "$archive" --directory "$staged"
      ${composeCommand} stop -t 30 actual-server
      mv "$data_dir" "$rollback"
      mv "$staged" "$data_dir"
      if ${composeCommand} start actual-server && ${composeCommand} up -d --wait actual-server; then
        rm -rf -- "$rollback"
        echo "Actual restore completed"
      else
        rm -rf -- "$data_dir"
        mv "$rollback" "$data_dir"
        ${composeCommand} start actual-server || true
        echo "restore failed; previous data was restored" >&2
        exit 1
      fi
    '';
  };
in
{
  options.my.actualStack = {
    enable = mkEnableOption "LAN-only Actual Budget application stack";
    hostname = mkOption {
      type = types.str;
      default = "REPLACE_WITH_LAN_HOSTNAME";
      description = "Reviewed LAN hostname served by Caddy's internal CA";
    };
    trustedLanCidrs = mkOption {
      type = types.listOf types.str;
      default = [ ];
      description = "Reviewed IPv4 and IPv6 source CIDRs allowed to reach HTTPS";
    };
    dataRoot = mkOption {
      type = types.path;
      default = "/var/lib/mini-pc";
      description = "Persistent runtime root outside the Nix store";
    };
    actualLoopbackPort = mkOption {
      type = types.port;
      default = 5006;
      description = "Host-loopback-only port used by native Caddy";
    };
    discordBot.enable = mkEnableOption "the Actual Discord bot";
    backupSchedule = mkOption {
      type = types.str;
      default = "03:15";
      description = "systemd calendar expression for consistent Actual backups";
    };
    backupRetentionDays = mkOption {
      type = types.ints.positive;
      default = 14;
      description = "Retention window for verified local pre-upgrade backups";
    };
    images = mkOption {
      type = types.attrsOf imageType;
      default = imageDefaults;
      description = "Typed immutable linux/amd64 image inventory";
    };
  };

  config = mkIf cfg.enable {
    assertions = [
      {
        assertion =
          !placeholder cfg.hostname && builtins.match "^[A-Za-z0-9][A-Za-z0-9.-]*$" cfg.hostname != null;
        message = "my.actualStack.hostname must be a reviewed LAN hostname";
      }
      {
        assertion = cfg.trustedLanCidrs != [ ] && builtins.all validCidr cfg.trustedLanCidrs;
        message = "my.actualStack.trustedLanCidrs must contain reviewed IPv4/IPv6 CIDRs";
      }
    ]
    ++ builtins.concatMap (
      name:
      let
        image = cfg.images.${name};
      in
      [
        {
          assertion = builtins.match digestPattern image.sourceDigest != null;
          message = "my.actualStack.images.${name}.sourceDigest must be an immutable sha256 digest";
        }
        {
          assertion = builtins.match digestPattern image.contentDigest != null;
          message = "my.actualStack.images.${name}.contentDigest must be an immutable sha256 digest";
        }
        {
          assertion = builtins.match hashPattern image.nixHash != null;
          message = "my.actualStack.images.${name}.nixHash must be a fixed-output SRI hash";
        }
        {
          assertion = !hasInfix ":latest" image.imageName && !hasInfix "@" image.imageName;
          message = "my.actualStack.images.${name}.imageName must not contain a mutable tag or digest";
        }
      ]
    ) activeImageNames;

    environment.systemPackages = [
      pkgs.docker-compose
      health
      loadImages
      backup
      restore
    ];
    networking.nftables.enable = true;
    networking.firewall.extraInputRules = concatStringsSep "\n" sourceRules;
    services.caddy = {
      enable = true;
      dataDir = "${cfg.dataRoot}/caddy";
      virtualHosts.${cfg.hostname}.extraConfig = ''
        tls internal
        encode gzip zstd
        reverse_proxy 127.0.0.1:${toString cfg.actualLoopbackPort}
      '';
    };
    systemd.tmpfiles.rules = [
      "d ${cfg.dataRoot} 0750 root caddy -"
      "d ${cfg.dataRoot}/actual 0750 root root -"
      "d ${cfg.dataRoot}/actual/data 0750 1001 1001 -"
      "d ${cfg.dataRoot}/caddy 0750 caddy caddy -"
      "d ${cfg.dataRoot}/secrets 0700 root root -"
      "d ${cfg.dataRoot}/backups 0700 root root -"
      "d ${cfg.dataRoot}/backups/actual 0700 root root -"
    ];

    systemd.services.mini-pc-image = {
      description = "Load immutable application images from the Nix closure";
      wantedBy = [ "multi-user.target" ];
      after = [ "docker.service" ];
      requires = [ "docker.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = lib.getExe loadImages;
      };
    };
    systemd.services.mini-pc-application = {
      description = "Actual Budget server";
      wantedBy = [ "multi-user.target" ];
      after = [
        "docker.service"
        "mini-pc-image.service"
      ];
      requires = [
        "docker.service"
        "mini-pc-image.service"
      ];
      environment = composeEnvironment;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${composeCommand} up -d --no-build --wait actual-server";
        ExecStop = "${composeCommand} stop -t 30 actual-server";
        TimeoutStartSec = 300;
        TimeoutStopSec = 60;
      };
    };
    systemd.services.mini-pc-discord-bot = mkIf cfg.discordBot.enable {
      description = "Actual Discord bot";
      wantedBy = [ "multi-user.target" ];
      after = [ "mini-pc-application.service" ];
      requires = [ "mini-pc-application.service" ];
      environment = composeEnvironment;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = "${composeCommand} --profile discord up -d --no-build --wait actual-discord-bot";
        ExecStop = "${composeCommand} --profile discord stop -t 30 actual-discord-bot";
        TimeoutStartSec = 300;
        TimeoutStopSec = 60;
      };
    };
    systemd.services.mini-pc-actual-backup = {
      description = "Consistent, verified Actual data backup";
      environment = composeEnvironment;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe backup;
        UMask = "0077";
      };
    };
    systemd.timers.mini-pc-actual-backup = {
      description = "Scheduled Actual data backup";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = cfg.backupSchedule;
        Persistent = true;
        RandomizedDelaySec = "15m";
        Unit = "mini-pc-actual-backup.service";
      };
    };
  };
}
