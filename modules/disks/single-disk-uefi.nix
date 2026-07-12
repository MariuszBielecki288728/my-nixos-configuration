{ config, lib, ... }:
{
  options.my.install.targetDisk = lib.mkOption {
    type = lib.types.str;
    default = "/dev/disk/by-id/REPLACE_DURING_INSTALL";
    description = "Stable path of the whole disk that disko is explicitly allowed to erase";
  };
  options.my.install.allowUnstableTestDisk = lib.mkOption {
    type = lib.types.bool;
    default = false;
    description = "Allow a /dev path only inside disposable VM layout tests";
  };

  config = {
    assertions = [
      {
        assertion =
          lib.hasPrefix "/dev/disk/by-id/" config.my.install.targetDisk
          || config.my.install.allowUnstableTestDisk;
        message = "my.install.targetDisk must be a stable /dev/disk/by-id path";
      }
    ];

    disko.devices.disk.main = {
      type = "disk";
      device = config.my.install.targetDisk;
      content = {
        type = "gpt";
        partitions = {
          ESP = {
            size = "1G";
            type = "EF00";
            content = {
              type = "filesystem";
              format = "vfat";
              mountpoint = "/boot";
              mountOptions = [ "umask=0077" ];
            };
          };
          root = {
            size = "100%";
            content = {
              type = "filesystem";
              format = "ext4";
              mountpoint = "/";
            };
          };
        };
      };
    };
  };
}
