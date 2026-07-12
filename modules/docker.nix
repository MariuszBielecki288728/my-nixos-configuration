{ pkgs, ... }:
{
  virtualisation.docker = {
    enable = true;
    # Docker 28 is marked insecure in the pinned nixpkgs revision. Docker 29 also
    # needs nft on its service PATH to program bridge/NAT rules correctly.
    package = pkgs.docker_29;
    extraPackages = [ pkgs.nftables ];
    autoPrune = {
      enable = true;
      dates = "weekly";
    };
  };
}
