{ pkgs }:
pkgs.testers.runNixOSTest {
  name = "shared-rescue-system";
  nodes.machine = { lib, ... }: {
    imports = [ ../rescue/system.nix ];
    virtualisation.emptyDiskImages = [ 1024 ];
    networking.firewall.enable = lib.mkForce false;
    boot.loader.grub.enable = false;
    fileSystems."/" = {
      device = "/dev/vda";
      fsType = "ext4";
    };
    system.stateVersion = "25.11";
  };
  testScript = ''

    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("sshd.service")
    machine.wait_for_unit("avahi-daemon.service")
    machine.succeed("systemctl is-active systemd-networkd")
    machine.succeed("command -v jq lspci lsusb dmidecode smartctl ethtool")
    machine.fail("systemctl cat autonomous-installer.service")
    before = machine.succeed("sha256sum /dev/vdb").strip()
    machine.sleep(5)
    after = machine.succeed("sha256sum /dev/vdb").strip()
    assert before == after, "rescue boot modified the disposable target disk"
  '';
}
