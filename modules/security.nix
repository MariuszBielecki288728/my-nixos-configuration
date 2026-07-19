{ ... }:
{
  networking.firewall = {
    enable = true;
    allowedTCPPorts = [ 22 ];
  };
  security.protectKernelImage = true;
  security.sudo.execWheelOnly = true;
}
