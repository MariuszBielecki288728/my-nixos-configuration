{ ... }:
{
  networking.useDHCP = false;
  networking.useNetworkd = true;
  systemd.network = {
    enable = true;
    networks."10-ethernet" = {
      matchConfig = {
        Type = "ether";
        # Without this exclusion, networkd can claim Docker's veth endpoints and
        # detach them from their bridge. Physical Ethernet has no veth kind.
        Kind = "!veth";
      };
      networkConfig = {
        DHCP = "yes";
        IPv6AcceptRA = true;
      };
    };
  };
  services.avahi = {
    enable = true;
    nssmdns4 = true;
    publish = {
      enable = true;
      addresses = true;
    };
  };
}
