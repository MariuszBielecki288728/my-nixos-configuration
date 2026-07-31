# Provisioning a mini PC

## Before starting

One local firmware session may be required to enable UEFI USB or PXE boot and choose
boot priority. The M710q does not provide AMT, vPro, remote KVM, or remote ISO
redirection. Wake-on-LAN can power a configured machine but cannot select a boot
device.

Keep private keys outside the repository. The rescue key authorizes temporary root
SSH; the admin key authorizes the installed non-root account. When no key flags are
given to the high-level command, it creates and reuses
`~/.ssh/mini_pc_provision_ed25519` for the invoking user.

## Preferred direct-Ethernet PXE workflow

Connect one dedicated cable between the provisioning PC and target. The temporary
network is isolated at `192.168.77.0/24`: the PC owns `192.168.77.1` and the target
receives `192.168.77.2`. The target needs no Internet access because rescue artifacts
are served locally and the installation closure is copied over SSH.

Review the interface first:

```bash
ip -brief link
ip route
sudo -E just -- provision-m710q \
  --interface REPLACE_WITH_DEDICATED_ETHERNET
```

The safety policy rejects a default-route interface, virtual interface, ambiguous
selection, existing global IPv4 address, or existing UDP/67 listener. The command
starts temporary DHCP/TFTP/HTTP, waits for rescue SSH, discovers hardware, displays
the selected disk identity, and requires its complete stable by-id path. Before the
installation reboot it disables PXE while retaining DHCP so PXE-first firmware can
fall through to the installed disk at the same address. Installed SSH and service
health must pass before success is reported. Cleanup removes the owned address and
temporary services on either success or failure.

In a bridged Linux VM, reserve the single lease for the target and exclude a Windows
adapter that also requests DHCP:

```bash
sudo -E just -- provision-m710q \
  --interface REPLACE_WITH_DEDICATED_ETHERNET \
  --ignore-client-mac REPLACE_WITH_WINDOWS_ADAPTER_MAC \
  --target-mac REPLACE_WITH_TARGET_MAC
```

Both MAC values are runtime-only. The ignore option is repeatable. Never commit an
observed interface or MAC as a generic default.

Every attempt writes private evidence to `artifacts/sessions/`, including metadata,
environment, discovery, disk selection, installation, verification, service logs, and
a best-effort journal. Failed session evidence is retained.

### WSL2 and VirtualBox

WSL2 commonly exposes only its virtual default-route interface, not a Windows cable
adapter as an independent Linux NIC. The safety policy correctly refuses to run the
direct-cable DHCP backend there. Use native Linux or a Linux VM whose second adapter
is bridged to the dedicated physical Ethernet port. A VirtualBox guest can use NAT for
management/downloads and the bridged adapter exclusively for provisioning. Keep the
VM running until installed-host verification finishes.

## USB rescue workflow

Build an SSH-accessible ISO by injecting a public key through an untracked wrapper:

```bash
scripts/build-iso.sh ~/.ssh/id_ed25519.pub
scripts/inspect-iso.sh "$(find -L result/iso -name '*.iso' -print -quit)"
```

Write it only from a host that exposes the reviewed removable whole device:

```bash
scripts/write-usb.sh \
  "$(find -L result/iso -name '*.iso' -print -quit)" \
  /dev/REVIEWED_USB_DEVICE
```

Boot rescue, wait for DHCP, then discover and install:

```bash
nix run .#discover -- root@nixos-rescue.local

nix run .#install -- \
  --target root@nixos-rescue.local \
  --host m710q \
  --identity ~/.ssh/id_ed25519 \
  --admin-key-file ~/.ssh/id_ed25519.pub \
  --installed-target admin@m710q.local
```

If more than one candidate remains, installation stops. Review the discovery report
and repeat with `--disk /dev/disk/by-id/REVIEWED_ID`. Never substitute `/dev/sda`.

On an existing home LAN, use these low-level SSH commands with the router-provided
address. Do not run the direct-Ethernet DHCP backend on that LAN.

## PXE artifacts and firmware

`nix build .#pxe-bundle` produces pinned `ipxe.efi`, TFTP and HTTP roots, a
store-path-correct boot script, and a manifest from the same rescue configuration as
the ISO. `pxe/build-pxe.sh` copies it into ignored generated directories without
overwriting an existing tree. The example dnsmasq configuration is opt-in and must
never be applied to a router or active LAN without reviewing address ownership.

The tested M710q order is Network/PXE, USB, internal disk: when PXE stops answering,
firmware falls through. Verify that behavior on each machine. USB, internal disk, PXE
is the conservative alternative.

## Troubleshooting

The session's `provisioning.log` distinguishes common failures:

| Symptom | Meaning | Safe response |
| --- | --- | --- |
| Installed Ubuntu eventually appears | PXE did not load and firmware fell through; the OS waited for networking | Check for the target's `DHCPDISCOVER`; do not treat this as installation success |
| DHCP identifies `MSFT 5.0` or the Windows hostname | the bridged host adapter requested the lease | exclude its reviewed MAC and reserve the target MAC |
| `no address available` | the single lease is reserved or stale | verify session-local reservation and lease state; do not delete unrelated host DHCP state |
| `PXEClient:Arch:00007` appears | 64-bit UEFI reached dnsmasq | continue with TFTP and iPXE logs |
| Rescue boots again after install | PXE delivery remained enabled | use the high-level transition or disable PXE before a manual reboot |
| SSH identity changed at `192.168.77.2` | rescue and installed systems use different host keys | use the session-private trust transition; do not disable checking globally |

Do not infer success from the target display. Completion requires installed `admin`
SSH, active `sshd`, Docker and application units, and passing health checks.
