{ modulesPath, ... }:
{
  imports = [
    "${modulesPath}/installer/netboot/netboot-minimal.nix"
    ./system.nix
  ];
}
