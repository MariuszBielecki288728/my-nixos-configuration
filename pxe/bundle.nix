{
  pkgs,
  rescueConfig,
  revision,
}:
let
  kernel = "${rescueConfig.system.build.kernel}/bzImage";
  initrd = "${rescueConfig.system.build.netbootRamdisk}/initrd";
  init = "${rescueConfig.system.build.toplevel}/init";
in
pkgs.runCommand "nixos-mini-pc-pxe-bundle" { nativeBuildInputs = [ pkgs.jq ]; } ''
  mkdir -p $out/nixos
  cp ${kernel} $out/nixos/bzImage
  cp ${initrd} $out/nixos/initrd
  cat >$out/nixos/boot.ipxe <<EOF
  #!ipxe
  dhcp
  kernel \''${base-url}/nixos/bzImage init=${init} loglevel=4
  initrd \''${base-url}/nixos/initrd
  boot
  EOF
  kernel_hash=$(sha256sum $out/nixos/bzImage | cut -d' ' -f1)
  initrd_hash=$(sha256sum $out/nixos/initrd | cut -d' ' -f1)
  jq -n \
    --arg revision ${pkgs.lib.escapeShellArg revision} \
    --arg kernel_sha256 "$kernel_hash" \
    --arg initrd_sha256 "$initrd_hash" \
    '{schema_version:"1.0",rescue_configuration:"rescue-pxe",git_revision:$revision,
      build_timestamp:"1970-01-01T00:00:01Z",kernel_sha256:$kernel_sha256,
      initrd_sha256:$initrd_sha256}' >$out/nixos/manifest.json
''
