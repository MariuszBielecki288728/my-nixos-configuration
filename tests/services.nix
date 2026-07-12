{ pkgs }:
let
  testImage = pkgs.dockerTools.buildLayeredImage {
    name = "mini-pc-test";
    tag = "ci-immutable";
    contents = [ pkgs.busybox ];
    extraCommands = ''
      mkdir -p www
      echo healthy > www/index.html
    '';
    config.Cmd = [
      "httpd"
      "-f"
      "-p"
      "80"
      "-h"
      "/www"
    ];
  };
in
pkgs.testers.runNixOSTest {
  name = "mini-pc-services";
  nodes.machine = { lib, ... }: {
    imports = [
      ../modules/users.nix
      ../modules/ssh.nix
      ../modules/docker.nix
      ../modules/application.nix
      ../modules/security.nix
    ];
    virtualisation.memorySize = 2048;
    virtualisation.diskSize = 4096;
    networking.firewall.enable = lib.mkForce false;
    my.application.image = "mini-pc-test:ci-immutable";
    systemd.services.load-test-image = {
      description = "Load immutable local application test image";
      after = [ "docker.service" ];
      requires = [ "docker.service" ];
      before = [ "mini-pc-application.service" ];
      requiredBy = [ "mini-pc-application.service" ];
      serviceConfig.Type = "oneshot";
      script = "${pkgs.docker_29}/bin/docker load < ${testImage}";
    };
    system.stateVersion = "25.11";
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("sshd.service")
    machine.succeed("sshd -T | grep -qx 'passwordauthentication no'")
    machine.succeed("sshd -T | grep -qx 'kbdinteractiveauthentication no'")
    machine.succeed("sshd -T | grep -qx 'permitrootlogin no'")
    machine.wait_for_unit("docker.service")
    machine.wait_until_succeeds("systemctl is-active mini-pc-application.service", timeout=300)
    machine.wait_until_succeeds("curl --fail --silent http://127.0.0.1:8080/ >/dev/null", timeout=120)
    machine.succeed("test $(stat -c %a /var/lib/mini-pc/secrets) = 700")
  '';
}
