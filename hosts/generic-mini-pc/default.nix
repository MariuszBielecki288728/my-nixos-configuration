{ lib, ... }:
{
  imports = [
    ../../modules/hardware/generic-x86_64.nix
    ../../modules/disks/single-disk-uefi.nix
    ../../modules/base.nix
    ../../modules/users.nix
    ../../modules/ssh.nix
    ../../modules/networking.nix
    ../../modules/docker.nix
    ../../modules/application.nix
    ../../modules/security.nix
    ../../modules/observability.nix
  ];

  networking.hostName = lib.mkDefault "mini-pc";
  system.stateVersion = "25.11";
}
