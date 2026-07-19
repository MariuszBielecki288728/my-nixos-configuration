{ ... }:
{
  imports = [ ../generic-mini-pc ];
  networking.hostName = "m710q";

  my.actualStack = {
    enable = true;
    hostname = "think-centre.home";
    trustedLanCidrs = [ "192.168.1.0/24" ];
    discordBot.enable = true;
  };
}
