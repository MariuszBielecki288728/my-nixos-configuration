# PXE/iPXE rescue delivery

Build the same rescue system used by the ISO:

```bash
nix build .#pxe-bundle
pxe/build-pxe.sh
```

The output contains pinned `tftp/ipxe.efi`,
`http/nixos/{boot.ipxe,bzImage,initrd}`, and `boot-manifest.json`. No mutable manual
download is required. The generated script derives its server from DHCP `next-server`
and uses the exact Nix store init path. `pxe/build-pxe.sh` copies the complete output
to ignored `pxe/generated/` without overwriting an existing tree.

Prefer `sudo -E just -- provision-m710q --interface INTERFACE` for a temporary,
automatically cleaned direct-cable server. `dnsmasq.conf.example` is an opt-in isolated
example; never apply it to a router or existing LAN without reviewing address ownership.

`just pxe-test` creates a disposable TAP, boots OVMF, receives iPXE through TFTP,
chains rescue through HTTP, verifies SSH and discovery, proves the disposable disk
unchanged, and removes the TAP.

Firmware behavior differs: test whether PXE-first falls through to the internal disk
when no PXE server answers. USB-first, internal-disk-second is the conservative order.
