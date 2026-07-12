{
  config,
  lib,
  pkgs,
  ...
}:
{
  imports = [
    ./networking.nix
    ./ssh.nix
    ./motd.nix
  ];

  options.my.rescue.authorizedKeys = lib.mkOption {
    type = lib.types.listOf lib.types.str;
    default = [ ];
    example = [ "ssh-ed25519 REPLACE_WITH_REAL_PUBLIC_KEY rescue-access" ];
    description = "Public keys allowed to log in as root in the rescue environment";
  };

  config = {
    networking.hostName = "nixos-rescue";
    environment.systemPackages = with pkgs; [
      cryptsetup
      curl
      dmidecode
      dosfstools
      ethtool
      gawk
      git
      gptfdisk
      iproute2
      jq
      lsof
      mdadm
      nvme-cli
      parted
      pciutils
      rsync
      smartmontools
      testdisk
      usbutils
    ];
    services.getty.helpLine = "Non-destructive rescue environment. Installation starts only by explicit remote command.";
    system.stateVersion = "25.11";
    warnings = lib.optional (config.my.rescue.authorizedKeys == [ ]) (
      "Rescue SSH has no authorized key; inject my.rescue.authorizedKeys before physical use"
    );

    assertions = [
      {
        assertion = !(config.systemd.services ? autonomous-installer);
        message = "The rescue environment must not contain an autonomous installer";
      }
    ];
  };
}
