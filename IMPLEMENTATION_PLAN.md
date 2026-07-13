# Generic NixOS Mini-PC Provisioning Repository — Implementation Plan

> Implementation note (2026-07): host-side provisioning has moved from the original
> Bash sketches in this plan to the UV-managed Python 3.14 package under `python/`.
> The safety architecture and CLI contracts remain authoritative; use `README.md`,
> `docs/SCRIPTS.md`, and command `--help` output for current paths and commands.

## 1. Objective

Create a repository that is the single source of truth for provisioning one or more x86_64 mini PCs, initially a Lenovo ThinkCentre M710q, without requiring a monitor or keyboard after BIOS boot settings are configured.

The repository must:

1. Define a reusable, mostly hardware-agnostic NixOS server configuration.
2. Build a generic rescue/install ISO that boots, acquires network access and exposes SSH.
3. Allow hardware discovery to be initiated remotely from the development PC.
4. Install the target system remotely through SSH using `nixos-anywhere` and `disko`.
5. Avoid automatic disk destruction immediately after booting the ISO.
6. Reuse the same configuration on other compatible mini PCs.
7. Start the required web application stack, initially through Docker Compose.
8. Reproduce the same observable machine state from the same Git commit and `flake.lock`.
9. Validate the configuration locally on Ubuntu under WSL2 where possible.
10. Run VM integration tests and full remote-install E2E tests in GitHub Actions.

The empty Git repository is assumed to exist and the shell is assumed to be open in its root.

---

## 2. Core Architecture

The preferred workflow is:

```text
Development PC running Ubuntu in WSL2
        |
        | build generic rescue ISO
        v
Mini PC boots the rescue environment
from USB, PXE/iPXE, or QEMU
        |
        | DHCP + SSH + public key
        v
Development PC connects remotely
        |
        | hardware discovery
        | disk selection and validation
        | nixos-anywhere + disko
        v
Installed NixOS system
        |
        | SSH + Docker Compose application
        v
Ready server
```

The ISO itself must not erase disks automatically.

The destructive operation begins only after an explicit remote command is run from the development PC.

---

## 3. Important Design Decisions

### 3.1 Use Nix flakes as the repository entry point

Use:

- `flake.nix` to define inputs and outputs;
- `flake.lock` to pin exact revisions;
- `nix develop` to provide all development tools;
- `nix flake check` as the main validation command;
- `nix build .#rescue-iso` to build the generic bootable ISO;
- `nix run .#discover -- root@HOST` to collect hardware facts;
- `nix run .#install -- --target root@HOST` to perform the controlled remote installation.

Commit both `flake.nix` and `flake.lock`.

### 3.2 The rescue ISO is generic and non-destructive

The rescue ISO should:

- boot on generic x86_64 UEFI hardware;
- use Ethernet and DHCP by default;
- expose SSH immediately;
- contain an authorized public key;
- provide useful diagnostic tools;
- include or have access to the repository flake;
- not partition or erase any disk automatically;
- support running `nixos-anywhere` from the development PC.

The ISO may expose a deterministic hostname such as:

```text
nixos-rescue
```

Optionally enable mDNS so that it can be reached as:

```text
nixos-rescue.local
```

### 3.3 Remote installation is preferred over autonomous installation

Use `nixos-anywhere` with `disko`.

The remote workflow should:

1. connect to the rescue ISO over SSH;
2. collect hardware information;
3. discover candidate disks;
4. select a disk using an explicit policy;
5. show the selected disk to the user or calling agent;
6. require explicit confirmation or a command-line flag;
7. invoke `nixos-anywhere`;
8. reboot into the installed system;
9. verify SSH and application health.

This is safer and more reusable than embedding Lenovo-specific DMI and disk identifiers into an auto-installing ISO.

### 3.4 Prefer a generic hardware module

Do not require a generated `hardware-configuration.nix` for the first implementation.

Create a reusable module for standard x86_64 UEFI mini PCs with common storage and USB drivers.

Use `disko` for filesystems and partition layout.

Add host-specific hardware overrides only if actual hardware requires them.

### 3.5 Use a generic single-disk policy

The initial installer should support a common case:

- exactly one non-removable internal disk;
- installer USB must be excluded;
- supported transport includes SATA and NVMe;
- ambiguous machines with multiple internal disks must require an explicit `--disk` argument.

Automatic disk selection may proceed only when exactly one safe candidate remains.

Never guess `/dev/sda`.

Prefer stable `/dev/disk/by-id/...` paths where possible.

### 3.6 Public keys may be committed; secrets may not

It is acceptable to commit:

- the SSH public key used to access the rescue ISO;
- the SSH public key installed for the normal user;
- test public keys.

Never commit:

- SSH private keys;
- age private keys;
- GitHub tokens;
- Tailscale auth keys;
- database passwords;
- TLS private keys;
- application secrets.

### 3.7 Docker Compose is acceptable initially

Use NixOS to manage:

- Docker;
- application files;
- a systemd unit that invokes Docker Compose;
- firewall rules;
- health checks.

Pin container images by digest.

---

## 4. Rescue Delivery Architecture

The rescue environment must be independent of its delivery mechanism.

The repository should define one shared rescue system and expose it through multiple outputs:

- a USB-bootable ISO;
- PXE/iPXE kernel, initrd and boot configuration;
- QEMU-compatible test artifacts.

The downstream provisioning workflow must remain identical:

```text
Boot rescue environment
        ↓
DHCP + SSH
        ↓
Remote discovery
        ↓
Safe disk selection
        ↓
nixos-anywhere + disko
        ↓
Reboot
        ↓
Verification
```

### 4.1 Shared rescue module

`rescue/system.nix` should contain common rescue behavior:

- networking;
- SSH;
- authorized public keys;
- mDNS;
- diagnostic tools;
- MOTD;
- no automatic installation service.

`rescue/iso.nix` and `rescue/pxe.nix` should be thin delivery-specific wrappers around that shared module.

Discovery and installation scripts must not inspect or depend on whether the machine booted from USB or PXE, except when excluding the active rescue medium from candidate disks.

### 4.2 USB path

USB remains the simplest first physical boot method.

The initial milestone should generate a hybrid UEFI-compatible rescue ISO and document writing it from native Linux or Windows. WSL raw USB access must not be assumed.

### 4.3 PXE/iPXE path

PXE support is a planned repository output, not a requirement for the first working physical installation.

The repository should eventually provide:

- rescue kernel and initrd artifacts;
- an example iPXE script;
- an example `dnsmasq` configuration;
- an HTTP-root layout;
- documentation for temporary and persistent PXE servers.

PXE must reuse the same rescue system as the USB ISO.

A recommended firmware boot order after one-time local setup is:

```text
Network/PXE
USB
Internal SSD
```

However, the actual order must be verified on the target machine. The design must not assume every UEFI firmware immediately falls through from an unavailable PXE server; DHCP/PXE timeout behavior should be tested.

An alternative conservative order is:

```text
USB
Internal SSD
Network/PXE
```

and PXE can be selected through a one-time firmware boot command if the firmware or operating system later provides one.

### 4.4 QEMU path

QEMU must boot the same rescue system used physically.

Tests should cover:

- ISO boot;
- PXE/iPXE boot where practical;
- SSH readiness;
- unchanged disposable disk before remote installation;
- the complete remote installation workflow.

### 4.5 Lenovo M710q target facts

The first target is:

```text
Model family: Lenovo ThinkCentre M710q / M710 Tiny
Machine type: 10MQ
Processor: Intel Pentium G4400T
Architecture: x86_64
```

The Lenovo platform specification lists manageability as `None` for this platform configuration and lists Wake-on-LAN support on the Intel Ethernet interface. Therefore the implementation must not depend on Intel AMT, vPro remote KVM, remote BIOS control or remote ISO redirection.

Wake-on-LAN may be added later for power control after the operating system and firmware are configured, but it does not replace boot-device selection.

Assume one local BIOS/UEFI setup session may be required to configure:

- USB boot;
- PXE/network boot if desired;
- boot priority;
- UEFI mode;
- power-on after AC loss;
- Wake-on-LAN;
- Secure Boot policy.

After that one-time setup, normal provisioning should be headless.

---

## 5. Development Host Assumptions

The development machine is Ubuntu running under WSL2.

### 5.1 Keep the repository inside the Linux filesystem

Prefer:

```text
~/src/nixos-mini-pc
```

Avoid `/mnt/c/...` because Nix and Git operations are slower and file semantics are less reliable there.

### 5.2 Enable systemd in WSL2

Check:

```bash
ps -p 1 -o comm=
```

If the result is not `systemd`, create or update `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Then run from Windows PowerShell:

```powershell
wsl --shutdown
```

Restart Ubuntu and verify PID 1 again.

### 5.3 Install base Ubuntu dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
  curl \
  git \
  xz-utils \
  ca-certificates \
  jq
```

Optional utilities:

```bash
sudo apt-get install -y \
  file \
  tree \
  shellcheck
```

### 5.4 Install Nix

With systemd enabled:

```bash
curl -L https://nixos.org/nix/install | sh -s -- --daemon
```

Without systemd:

```bash
curl -L https://nixos.org/nix/install | sh -s -- --no-daemon
```

Enable flakes in `/etc/nix/nix.conf`:

```ini
experimental-features = nix-command flakes
```

Verify:

```bash
nix --version
nix flake --help >/dev/null
```

### 5.5 WSL networking considerations

The easiest supported deployment topology is:

```text
PC and mini PC connected to the same router or switch
```

Direct Ethernet may work, but WSL networking can complicate access to a separately addressed physical adapter.

The implementation should assume shared-LAN DHCP first.

The rescue ISO should support:

- DHCP;
- mDNS;
- SSH;
- printing its IP address to the console and journal.

### 5.6 WSL virtualization limitations

Assume:

- formatting, evaluation and builds run locally;
- NixOS VM tests may run locally;
- full ISO boot and remote-install E2E may be slow without KVM;
- GitHub Actions runs the mandatory E2E;
- a self-hosted Linux runner with KVM may be added later.

---

## 6. Proposed Repository Structure

```text
.
├── AGENTS.md
├── IMPLEMENTATION_PLAN.md
├── README.md
├── LICENSE
├── flake.nix
├── flake.lock
├── .editorconfig
├── .gitignore
├── .envrc.example
├── Justfile
│
├── hosts/
│   ├── generic-mini-pc/
│   │   └── default.nix
│   ├── m710q/
│   │   └── default.nix
│   └── e2e-target/
│       └── default.nix
│
├── modules/
│   ├── base.nix
│   ├── users.nix
│   ├── ssh.nix
│   ├── networking.nix
│   ├── docker.nix
│   ├── application.nix
│   ├── security.nix
│   ├── observability.nix
│   ├── hardware/
│   │   └── generic-x86_64.nix
│   └── disks/
│       └── single-disk-uefi.nix
│
├── rescue/
│   ├── system.nix
│   ├── iso.nix
│   ├── pxe.nix
│   ├── networking.nix
│   ├── ssh.nix
│   └── motd.nix
│
├── pxe/
│   ├── build-pxe.sh
│   ├── dnsmasq.conf.example
│   ├── ipxe-menu.ipxe
│   ├── http-root/
│   │   └── .gitkeep
│   └── README.md
│
├── provisioning/
│   ├── discover-hardware.sh
│   ├── select-disk.sh
│   ├── install.sh
│   ├── verify-installed.sh
│   └── lib/
│       ├── common.sh
│       ├── remote.sh
│       └── disks.sh
│
├── application/
│   ├── compose.yaml
│   ├── .env.example
│   └── README.md
│
├── tests/
│   ├── services.nix
│   ├── disk-layout.nix
│   ├── rescue-iso.nix
│   ├── e2e/
│   │   ├── run.sh
│   │   ├── start-rescue-vm.sh
│   │   ├── wait-for-ssh.sh
│   │   └── collect-logs.sh
│   └── fixtures/
│       └── test-ssh-key.pub
│
├── scripts/
│   ├── check.sh
│   ├── build-iso.sh
│   ├── run-rescue-vm.sh
│   ├── inspect-iso.sh
│   └── write-usb.sh
│
└── .github/
    ├── workflows/
    │   ├── check.yaml
    │   ├── provisioning-e2e.yaml
    │   └── release-iso.yaml
    └── dependabot.yml
```

---

## 7. Proposed Core File Contents

The snippets below are starting points. Validate actual option names against pinned inputs.

### 7.1 `flake.nix`

Responsibilities:

- pin `nixpkgs`, `disko` and `nixos-anywhere`;
- expose host configurations;
- expose rescue ISO;
- expose development shell;
- expose checks;
- expose `discover` and `install` apps;
- expose formatter.

Proposed shape:

```nix
{
  description = "Generic NixOS mini-PC provisioning and rescue ISO";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nixos-anywhere = {
      url = "github:nix-community/nixos-anywhere";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs@{ self, nixpkgs, disko, nixos-anywhere, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      lib = nixpkgs.lib;
    in {
      formatter.${system} = pkgs.nixfmt-rfc-style;

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          git
          just
          jq
          shellcheck
          shfmt
          nixfmt-rfc-style
          qemu
          openssh
          curl
          coreutils
          iproute2
        ];
      };

      nixosConfigurations.generic-mini-pc = lib.nixosSystem {
        inherit system;
        specialArgs = { inherit inputs; };
        modules = [
          disko.nixosModules.disko
          ./hosts/generic-mini-pc
        ];
      };

      nixosConfigurations.m710q = lib.nixosSystem {
        inherit system;
        specialArgs = { inherit inputs; };
        modules = [
          disko.nixosModules.disko
          ./hosts/m710q
        ];
      };

      nixosConfigurations.e2e-target = lib.nixosSystem {
        inherit system;
        specialArgs = { inherit inputs; };
        modules = [
          disko.nixosModules.disko
          ./hosts/e2e-target
        ];
      };

      nixosConfigurations.rescue = lib.nixosSystem {
        inherit system;
        specialArgs = { inherit inputs; };
        modules = [
          ./rescue/iso.nix
        ];
      };

      packages.${system}.rescue-iso =
        self.nixosConfigurations.rescue.config.system.build.isoImage;

      apps.${system}.discover = {
        type = "app";
        program = "${pkgs.writeShellScript "discover" ''
          exec ${./provisioning/discover-hardware.sh} "$@"
        ''}";
      };

      apps.${system}.install = {
        type = "app";
        program = "${pkgs.writeShellScript "install" ''
          exec ${./provisioning/install.sh} "$@"
        ''}";
      };

      checks.${system} = {
        generic-system =
          self.nixosConfigurations.generic-mini-pc.config.system.build.toplevel;

        m710q-system =
          self.nixosConfigurations.m710q.config.system.build.toplevel;

        rescue-iso =
          self.nixosConfigurations.rescue.config.system.build.isoImage;

        services = import ./tests/services.nix {
          inherit pkgs inputs;
        };
      };
    };
}
```

Use the stable NixOS branch intended at implementation time.

### 7.2 `hosts/generic-mini-pc/default.nix`

```nix
{ ... }:

{
  imports = [
    ../../modules/hardware/generic-x86_64.nix
    ../../modules/disks/single-disk-uefi.nix
    ../../modules/base.nix
    ../../modules/users.nix
    ../../modules/ssh.nix
    ../../modules/networking.nix
    ../../modules/docker.nix
    ../../modules/application.nix
    ../../modules/security.nix
    ../../modules/observability.nix
  ];

  networking.hostName = "mini-pc";

  my.install.targetDisk = "/dev/disk/by-id/REPLACE_DURING_INSTALL";

  system.stateVersion = "25.11";
}
```

The disk value shown here is a placeholder. The install wrapper must override it using runtime-generated Nix configuration or `nixos-anywhere` extra files.

### 7.3 `hosts/m710q/default.nix`

```nix
{ ... }:

{
  imports = [
    ../generic-mini-pc
  ];

  networking.hostName = "m710q";

  # Add Lenovo-specific overrides only when they are proven necessary.
}
```

The M710q host should initially contain almost no hardware-specific declarations.

### 7.4 `hosts/e2e-target/default.nix`

This test target should import the same generic modules but use a stable QEMU virtual disk path.

```nix
{ ... }:

{
  imports = [
    ../generic-mini-pc
  ];

  networking.hostName = "e2e-target";

  my.install.targetDisk = "/dev/disk/by-id/virtio-nixos-e2e";
}
```

### 7.5 `modules/hardware/generic-x86_64.nix`

```nix
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

  boot.kernelModules = [ ];

  hardware.enableRedistributableFirmware = true;
}
```

This should remain small and generic.

### 7.6 `modules/disks/single-disk-uefi.nix`

Define a custom option:

```nix
{ lib, config, ... }:

{
  options.my.install.targetDisk = lib.mkOption {
    type = lib.types.str;
    description = "Disk to erase and provision with disko";
  };

  config = {
    assertions = [
      {
        assertion = config.my.install.targetDisk != "";
        message = "my.install.targetDisk must be set explicitly";
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
```

### 7.7 Networking module

Use a portable Ethernet DHCP configuration.

Prefer systemd-networkd matching on Ethernet device type instead of a concrete interface name.

Conceptual form:

```nix
{ ... }:

{
  networking.useNetworkd = true;
  networking.useDHCP = false;

  systemd.network = {
    enable = true;

    networks."10-ethernet" = {
      matchConfig.Type = "ether";
      networkConfig = {
        DHCP = "yes";
        IPv6AcceptRA = true;
      };
    };
  };

  services.avahi = {
    enable = true;
    nssmdns4 = true;
    publish = {
      enable = true;
      addresses = true;
    };
  };
}
```

The rescue environment and installed system may use separate hostnames.

### 7.8 Shared rescue system and ISO wrapper

`rescue/system.nix` should define the common rescue environment. `rescue/iso.nix` should import it and add ISO-specific settings.

The shared rescue system should:

- import the standard minimal installation CD;
- import rescue networking and SSH modules;
- enable mDNS;
- include `git`, `jq`, `lsblk`, `lspci`, `ethtool`, `smartmontools` and other discovery tools;
- display connection instructions in MOTD;
- never start installation automatically.

Conceptual form:

```nix
{ modulesPath, pkgs, ... }:

{
  imports = [
    "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
    ./networking.nix
    ./ssh.nix
    ./motd.nix
  ];

  networking.hostName = "nixos-rescue";

  isoImage.isoName = "nixos-mini-pc-rescue.iso";

  environment.systemPackages = with pkgs; [
    git
    jq
    pciutils
    usbutils
    smartmontools
    ethtool
    dmidecode
    parted
    gptfdisk
    rsync
  ];
}
```


### 7.9 PXE/iPXE output

`rescue/pxe.nix` should expose the kernel and initrd needed for network boot while importing the same shared rescue module.

The repository should provide an example iPXE script resembling:

```ipxe
#!ipxe
dhcp
kernel http://${next-server}/nixos/bzImage init=/nix/store/.../init loglevel=4
initrd http://${next-server}/nixos/initrd
boot
```

The actual generated kernel parameters and store paths must be produced by the build, not copied manually into documentation.

`pxe/build-pxe.sh` should assemble a versioned HTTP root containing:

```text
http-root/
└── nixos/
    ├── bzImage
    ├── initrd
    ├── boot.ipxe
    └── manifest.json
```

The manifest should record:

- Git commit;
- flake-lock revision;
- hashes of the kernel and initrd;
- build timestamp;
- rescue configuration name.

The example PXE server must be opt-in and must not modify the user's existing router DHCP configuration automatically.

### 7.10 Rescue SSH

```nix
{ ... }:

{
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-ed25519 REPLACE_WITH_REAL_PUBLIC_KEY rescue-access"
  ];
}
```

### 7.11 `provisioning/discover-hardware.sh`

Usage:

```bash
nix run .#discover -- root@nixos-rescue.local
```

Required behavior:

1. connect over SSH;
2. collect DMI data;
3. collect block-device data in machine-readable format;
4. collect `/dev/disk/by-id` links;
5. collect network interfaces and addresses;
6. collect PCI and USB devices;
7. save a JSON report locally;
8. print safe disk candidates;
9. never modify the remote machine.

Suggested remote commands:

```bash
cat /sys/class/dmi/id/sys_vendor
cat /sys/class/dmi/id/product_name
cat /sys/class/dmi/id/product_version
lsblk --json --bytes --output NAME,PATH,SIZE,MODEL,SERIAL,TRAN,RM,ROTA,TYPE,FSTYPE,MOUNTPOINTS
find -L /dev/disk/by-id -maxdepth 1 -type l -printf '%f -> %l\n'
ip -json address
lspci -nn
lsusb
```

Output path:

```text
artifacts/discovery/<timestamp>-<hostname>.json
```

Do not commit reports containing serial numbers unless intentionally desired.

### 7.12 `provisioning/select-disk.sh`

Disk-selection policy:

1. enumerate block devices of type `disk`;
2. exclude `RM=1`;
3. exclude transport `usb`;
4. exclude the device backing the rescue ISO;
5. exclude disks with mounted child partitions;
6. resolve a stable `/dev/disk/by-id` link;
7. if exactly one candidate remains, select it;
8. if multiple candidates remain, fail and require `--disk`;
9. print model, serial, size and resolved path;
10. never erase anything.

The script should produce one value only on success:

```text
/dev/disk/by-id/...
```

### 7.13 `provisioning/install.sh`

Suggested interface:

```bash
nix run .#install -- \
  --target root@nixos-rescue.local \
  --host m710q
```

Optional explicit disk:

```bash
nix run .#install -- \
  --target root@nixos-rescue.local \
  --host generic-mini-pc \
  --disk /dev/disk/by-id/...
```

Required behavior:

1. parse arguments;
2. verify SSH access;
3. invoke hardware discovery;
4. select or validate the disk;
5. display a destructive action summary;
6. require explicit confirmation unless `--yes` is passed;
7. generate a temporary Nix module overriding `my.install.targetDisk`;
8. invoke pinned `nixos-anywhere`;
9. wait for reboot;
10. connect to the installed hostname or previous IP;
11. verify SSH;
12. verify systemd services;
13. verify application health.

Example confirmation:

```text
Target host: root@nixos-rescue.local
Target configuration: m710q
Disk to erase: /dev/disk/by-id/ata-SAMSUNG_...
Model: Samsung SSD ...
Size: 256 GB

Type the full disk path to continue:
```

`--yes` should be intended for CI only and clearly documented.

### 7.14 Integrating runtime disk selection with `nixos-anywhere`

The install script should create a temporary module:

```nix
{
  my.install.targetDisk = "/dev/disk/by-id/...";
}
```

Then pass it as an extra module to the target configuration.

Possible implementation approaches:

- create a temporary wrapper flake;
- use `--extra-files`;
- generate a temporary configuration output;
- use a flake override module supported by the chosen workflow.

Select the simplest approach that remains reproducible and testable.

Do not edit tracked files merely to insert the current disk path.

### 7.15 Application module

Retain the previous design:

- Docker enabled by NixOS;
- Compose project copied from the repository;
- systemd unit starts it;
- images pinned by digest;
- health endpoint tested;
- secrets not stored in the Nix store.

### 7.16 NixOS service tests

Test reusable service modules without disk or rescue logic.

Verify:

- SSH active;
- password authentication disabled;
- root login disabled;
- Docker active;
- application service active;
- application health succeeds.

### 7.17 Rescue delivery tests

Add tests for the shared rescue configuration and its delivery wrappers.

At minimum, verify:

- ISO boot succeeds;
- DHCP succeeds;
- SSH starts;
- mDNS service starts;
- diagnostic tools exist;
- no installation service exists;
- no disk modification occurs.

When PXE support is implemented, add a PXE/iPXE boot test that reaches the same SSH-ready rescue state.

### 7.18 Full provisioning E2E

The E2E must exercise the preferred real workflow:

```text
build rescue ISO
        ↓
boot rescue ISO in QEMU
        ↓
connect over SSH
        ↓
run discovery
        ↓
select disposable virtio disk
        ↓
run nixos-anywhere
        ↓
reboot from installed disk
        ↓
verify SSH and HTTP
```

The E2E target must use:

- a blank qcow2 disk;
- a deterministic virtual disk serial;
- a dedicated test public key;
- a dedicated private key generated in CI;
- port forwarding for SSH and HTTP;
- a strict global timeout;
- log collection.

The test must prove that simply booting the rescue ISO does not erase the disk.

---

## 8. GitHub Actions Plan

### 8.1 `check.yaml`

Run:

- formatting;
- flake evaluation;
- host builds;
- service VM test;
- rescue ISO build;
- rescue ISO test.

### 8.2 `provisioning-e2e.yaml`

Run the full remote workflow:

1. build ISO;
2. create disposable disk;
3. boot rescue VM;
4. wait for SSH;
5. run `nix run .#discover`;
6. run `nix run .#install -- --yes`;
7. reboot;
8. verify installed system;
9. collect logs.

Run manually and on relevant changes.

### 8.3 Self-hosted runner

If GitHub-hosted emulation is too slow, move only the full E2E to:

```yaml
runs-on: [self-hosted, linux, x86_64, kvm]
```

Keep fast checks on GitHub-hosted runners.

---

## 9. Local Development Workflow

```bash
nix develop
just fmt
just check
```

Build rescue ISO:

```bash
nix build .#rescue-iso
```

Run service tests:

```bash
nix build .#checks.x86_64-linux.services --print-build-logs
```

Run rescue VM:

```bash
just run-rescue-vm
```

Discover a real machine:

```bash
nix run .#discover -- root@nixos-rescue.local
```

Install a real machine:

```bash
nix run .#install -- \
  --target root@nixos-rescue.local \
  --host m710q
```

---

## 10. Implementation Phases

### Phase 0 — Bootstrap

Create:

- flake;
- lock file;
- development shell;
- formatter;
- Justfile;
- README;
- AGENTS.md.

### Phase 0.5 — Provisioning architecture contract

Before implementing service modules, document and test the boundaries between:

```text
rescue delivery
    -> SSH transport
    -> hardware discovery JSON
    -> disk selection
    -> runtime disk override
    -> nixos-anywhere
    -> installed-system verification
```

Deliverables:

- a short architecture diagram in `README.md`;
- command-line interfaces for `discover` and `install`;
- a versioned discovery-report schema;
- a documented disk-selector input/output contract;
- a decision that provisioning logic begins only after SSH is available;
- no coupling between provisioning logic and USB/PXE/QEMU delivery.

### Phase 1 — Generic target system

Implement:

- generic hardware;
- users;
- SSH;
- networking;
- Docker;
- application;
- security;
- service tests.

### Phase 2 — Generic disk module

Implement:

- parameterized target disk option;
- UEFI GPT layout;
- disk-layout tests.

### Phase 3 — Non-destructive rescue ISO

Implement:

- DHCP;
- mDNS;
- SSH;
- public key;
- diagnostic tools;
- MOTD;
- ISO VM test.

No destructive behavior is allowed in this phase.

### Phase 4 — Remote hardware discovery

Implement:

- discovery script;
- JSON report;
- safe candidate disk listing;
- no modification behavior.

### Phase 5 — Remote installer

Implement:

- disk selection;
- explicit confirmation;
- runtime disk module override;
- `nixos-anywhere`;
- post-install verification.

### Phase 6 — Full E2E

Test:

- rescue boot;
- SSH;
- discovery;
- disk selection;
- remote install;
- reboot;
- SSH;
- application health.

### Phase 7 — GitHub Actions

Add check, E2E and release workflows.

### Phase 7.5 — PXE/iPXE delivery

After the USB rescue path is stable:

- expose shared rescue kernel and initrd artifacts;
- generate an iPXE script;
- provide example `dnsmasq` and HTTP layouts;
- test PXE boot in QEMU;
- document one-time Lenovo firmware configuration;
- do not require PXE for the first physical deployment.

### Phase 8 — Physical Lenovo test

1. build rescue ISO;
2. write it to USB;
3. boot Lenovo;
4. connect over SSH;
5. run discovery;
6. review disk candidate;
7. run installer;
8. verify installed system.

No Lenovo-specific disk identifiers should be added unless a real incompatibility requires them.

For the known 10MQ / Pentium G4400T target:

- do not plan around Intel AMT or remote KVM;
- optionally enable Wake-on-LAN after installation;
- expect one local BIOS/UEFI session for boot-order configuration;
- test whether PXE-first reliably falls through to the internal SSD when no PXE service is available.

---

## 11. USB Writing

`scripts/write-usb.sh` must:

- require explicit ISO and block-device arguments;
- refuse non-removable targets by default;
- print model and size;
- require typing the full device path;
- never auto-select a disk;
- use `dd` with progress and sync;
- clearly state that raw USB access may not work from WSL.

A Windows image writer may be used for the actual USB creation.

---

## 12. Reusability Goals

The same rescue ISO should be usable on:

- Lenovo M710q;
- similar ThinkCentre Tiny systems;
- Intel NUC-class systems;
- generic x86_64 UEFI mini PCs;
- QEMU test machines.

A new host should normally require only:

```text
hosts/<hostname>/default.nix
```

containing:

- hostname;
- optional service differences;
- optional hardware overrides;
- no fixed disk ID.

The disk path is selected at install time.

---

## 13. Safety Requirements

The implementation must guarantee:

- booting the ISO alone is non-destructive;
- discovery is read-only;
- automatic selection works only with exactly one safe internal disk;
- ambiguous disk layouts fail closed;
- explicit disk arguments are validated remotely;
- installation prints a destructive summary;
- interactive use requires full disk-path confirmation;
- CI uses `--yes` only with disposable qcow2 disks;
- installer USB and mounted disks are excluded;
- no tracked file is rewritten to store a machine-specific disk path.

---

## 14. Initial Completion Criteria

The repository is ready for the first physical test when:

- [ ] `nix flake check` passes.
- [ ] Generic target closure builds.
- [ ] M710q target closure builds.
- [ ] Rescue ISO builds.
- [ ] Shared rescue configuration is independent of delivery medium.
- [ ] Rescue ISO VM test passes.
- [ ] Provisioning scripts do not depend on USB-specific paths.
- [ ] PXE output is either implemented and tested or explicitly tracked as the next delivery milestone.
- [ ] Service VM tests pass.
- [ ] Disk-layout test passes.
- [ ] Discovery script produces valid JSON.
- [ ] Discovery makes no disk changes.
- [ ] Disk selector chooses exactly one safe virtual disk.
- [ ] Disk selector rejects ambiguous layouts.
- [ ] Full provisioning E2E passes.
- [ ] Installed-system SSH works.
- [ ] Password SSH and root login are rejected.
- [ ] Docker and application health checks pass.
- [ ] Booting rescue ISO without running install leaves the disk unchanged.
- [ ] No private keys or plaintext secrets are present.
- [ ] README documents WSL limitations and the full physical workflow.

The first physical deployment should use the generic rescue ISO and remote installer. It should not require adding Lenovo DMI values or a fixed SSD identifier to the repository.
