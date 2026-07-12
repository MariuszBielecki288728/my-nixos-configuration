{ modulesPath, ... }:
{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
    ./system.nix
  ];
  image.fileName = "nixos-mini-pc-rescue.iso";
}
