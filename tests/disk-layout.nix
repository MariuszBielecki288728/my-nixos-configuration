{ pkgs, disko }:
pkgs.testers.runNixOSTest {
  name = "single-disk-uefi-layout";
  nodes.machine = { config, ... }: {
    imports = [
      disko.nixosModules.disko
      ../modules/disks/single-disk-uefi.nix
    ];
    my.install.targetDisk = "/dev/vdb";
    my.install.allowUnstableTestDisk = true;
    virtualisation.emptyDiskImages = [ 4096 ];
    boot.loader.grub.enable = false;
    fileSystems."/" = {
      device = "/dev/vda";
      fsType = "ext4";
    };
    system.stateVersion = "25.11";
    environment.systemPackages = [
      (pkgs.writeShellScriptBin "run-disko-layout" ''
        exec ${config.system.build.diskoScript}
      '')
    ];
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("run-disko-layout")
    machine.succeed("lsblk -no PARTTYPE /dev/vdb1 | grep -qi c12a7328-f81f-11d2-ba4b-00a0c93ec93b")
    machine.succeed("lsblk -no FSTYPE /dev/vdb1 | grep -qx vfat")
    machine.succeed("lsblk -no FSTYPE /dev/vdb2 | grep -qx ext4")
  '';
}
