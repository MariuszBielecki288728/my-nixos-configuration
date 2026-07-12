{ ... }:
{
  networking.firewall = {
    enable = true;
    allowedTCPPorts = [
      22
      8080
    ];
  };
  security.protectKernelImage = true;
  security.sudo.execWheelOnly = true;
}
