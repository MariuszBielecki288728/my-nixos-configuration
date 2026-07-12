{ config, lib, ... }:
{
  options.my.ssh.authorizedKeys = lib.mkOption {
    type = lib.types.listOf lib.types.str;
    default = [ ];
    example = [ "ssh-ed25519 REPLACE_WITH_REAL_PUBLIC_KEY admin" ];
    description = "Public SSH keys authorized for the administrator account";
  };

  config = {
    users.mutableUsers = false;
    # Evaluation remains possible before a real public key is supplied. The install
    # wrapper always injects a key, and the warning below makes this state visible.
    users.allowNoPasswordLogin = config.my.ssh.authorizedKeys == [ ];
    users.users.admin = {
      isNormalUser = true;
      extraGroups = [ "wheel" ];
      openssh.authorizedKeys.keys = config.my.ssh.authorizedKeys;
    };
    security.sudo.wheelNeedsPassword = false;
    warnings = lib.optional (config.my.ssh.authorizedKeys == [ ]) (
      "No admin SSH public key is configured; inject one before physical installation"
    );
  };
}
