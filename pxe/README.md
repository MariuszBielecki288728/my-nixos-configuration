# PXE/iPXE rescue delivery

Build the same rescue system used by the ISO:

```bash
nix build .#pxe-bundle
pxe/build-pxe.sh
```

Serve `pxe/http-root` over HTTP and configure iPXE to load `ipxe-menu.ipxe` after
replacing the visible server placeholder. The generated `boot.ipxe` requires the
`base-url` variable supplied by that menu. `dnsmasq.conf.example` is deliberately an
opt-in isolated-LAN example. Never apply it to a router or an existing DHCP server
without reviewing interface and address ownership.

Firmware behavior differs: test whether PXE-first falls through to the internal disk
when no PXE server answers. USB-first, internal-disk-second is the conservative order.
