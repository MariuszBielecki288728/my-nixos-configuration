{ pkgs, ... }:
{
  users.motd = ''
    NixOS mini-PC rescue environment
    This system never installs or erases disks automatically.
    Connect with: ssh root@nixos-rescue.local
  '';
  systemd.services.rescue-connection-info = {
    description = "Print rescue connection information";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    serviceConfig.Type = "oneshot";
    script = ''
      echo "Rescue environment is ready; no disk installation service is enabled."
      ${pkgs.iproute2}/bin/ip -brief address
    '';
  };
}
