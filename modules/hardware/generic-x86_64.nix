{ lib, ... }:
{
  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  boot.initrd.availableKernelModules = [
    "xhci_pci"
    "ahci"
    "nvme"
    "usb_storage"
    "sd_mod"
    "virtio_pci"
    "virtio_blk"
    "virtio_scsi"
  ];
  hardware.enableRedistributableFirmware = true;
}
