{ lib, ... }:
{
  imports = [ ../generic-mini-pc ];
  nixpkgs.config.allowUnfreePredicate = package: lib.getName package == "netdata";
  networking.hostName = "m710q";

  my.actualStack = {
    enable = true;
    hostname = "think-centre.home";
    trustedLanCidrs = [ "192.168.1.0/24" ];
    discordBot.enable = true;
  };

  my.deviceMonitoring = {
    enable = true;
    hostname = "think-centre.home";
    trustedLanCidrs = [ "192.168.1.0/24" ];
  };
}
