{ ... }:
{
  imports = [ ../generic-mini-pc ];
  networking.hostName = "e2e-target";
  my.install.targetDisk = "/dev/disk/by-id/virtio-nixos-e2e";
  my.actualStack = {
    enable = true;
    hostname = "actual.e2e.test";
    trustedLanCidrs = [ "10.0.2.0/24" ];
  };
}
