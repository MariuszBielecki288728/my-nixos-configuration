{ ... }:
{
  imports = [ ../generic-mini-pc ];
  networking.hostName = "e2e-target";
  my.install.targetDisk = "/dev/disk/by-id/virtio-nixos-e2e";
}
