{
  pkgs,
  rescueConfig,
  revision,
  nixpkgsRevision,
}:
let
  kernel = "${rescueConfig.system.build.kernel}/bzImage";
  initrd = "${rescueConfig.system.build.netbootRamdisk}/initrd";
  init = "${rescueConfig.system.build.toplevel}/init";
in
pkgs.runCommand "nixos-mini-pc-pxe-bundle" { nativeBuildInputs = [ pkgs.jq ]; } ''

  mkdir -p $out/http/nixos $out/tftp
  cp ${kernel} $out/http/nixos/bzImage
  cp ${initrd} $out/http/nixos/initrd
  cp ${pkgs.ipxe}/ipxe.efi $out/tftp/ipxe.efi
  cat >$out/http/nixos/boot.ipxe <<EOF
  #!ipxe
  kernel http://\''${next-server}:8081/nixos/bzImage init=${init} initrd=initrd nohibernate loglevel=4 lsm=landlock,yama,bpf console=ttyS0,115200n8
  initrd http://\''${next-server}:8081/nixos/initrd
  boot
  EOF
  kernel_hash=$(sha256sum $out/http/nixos/bzImage | cut -d' ' -f1)
  initrd_hash=$(sha256sum $out/http/nixos/initrd | cut -d' ' -f1)
  ipxe_hash=$(sha256sum $out/tftp/ipxe.efi | cut -d' ' -f1)
  jq -n \
    --arg revision ${pkgs.lib.escapeShellArg revision} \
    --arg nixpkgs_revision ${pkgs.lib.escapeShellArg nixpkgsRevision} \
    --arg kernel_sha256 "$kernel_hash" \
    --arg initrd_sha256 "$initrd_hash" \
    --arg ipxe_sha256 "$ipxe_hash" \
    '{schema_version:"1.0",rescue_configuration:"rescue-pxe",git_revision:$revision,
      nixpkgs_revision:$nixpkgs_revision,build_timestamp:"1970-01-01T00:00:01Z",
      artifacts:{kernel:{path:"http/nixos/bzImage",sha256:$kernel_sha256},
        initrd:{path:"http/nixos/initrd",sha256:$initrd_sha256},
        ipxe:{path:"tftp/ipxe.efi",sha256:$ipxe_sha256}}}' >$out/boot-manifest.json
''
