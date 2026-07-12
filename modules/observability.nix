{ ... }:
{
  services.journald.extraConfig = ''
    Storage=persistent
    SystemMaxUse=512M
  '';
  boot.kernel.sysctl."kernel.dmesg_restrict" = 1;
}
