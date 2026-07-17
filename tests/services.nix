{ pkgs }:
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
    machine.wait_for_unit("mini-pc-image.service")
    machine.succeed("docker image inspect docker.io/library/nginx@sha256:dc8e6d3967a06c0c9bb10d16cfc5770686de05da4c34d4224ef2aec61142e8f1")
    machine.wait_until_succeeds("systemctl is-active mini-pc-application.service", timeout=300)
    machine.wait_until_succeeds("curl --fail --silent http://127.0.0.1:8080/ >/dev/null", timeout=120)
    machine.succeed("test $(stat -c %a /var/lib/mini-pc/secrets) = 700")
  '';
}
