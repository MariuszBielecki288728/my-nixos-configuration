{
  description = "Generic, safe NixOS mini-PC provisioning";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nixos-anywhere = {
      url = "github:nix-community/nixos-anywhere";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.disko.follows = "disko";
    };
  };

  outputs =
    inputs@{
      self,
      nixpkgs,
      disko,
      nixos-anywhere,
      ...
    }:
    let
      system = "x86_64-linux";
      lib = nixpkgs.lib;
      pkgs = import nixpkgs { inherit system; };
      mkHost =
        module:
        lib.nixosSystem {
          inherit system;
          specialArgs = { inherit inputs; };
          modules = [
            disko.nixosModules.disko
            module
          ];
        };
      pythonProvisioning = pkgs.python314Packages.buildPythonApplication {
        pname = "mini-pc-provision";
        version = "0.1.0";
        src = ./python;
        pyproject = true;
        build-system = [ pkgs.python314Packages.hatchling ];
      };
      pythonCommand =
        name: subcommand: runtimeInputs:
        pkgs.writeShellApplication {
          inherit name;
          runtimeInputs = [ pythonProvisioning ] ++ runtimeInputs;
          text = ''
            export PROJECT_ROOT=${self}
            exec mini-pc-provision ${subcommand} "$@"
          '';
        };
    in
    {
      formatter.${system} = pkgs.nixfmt-rfc-style;

      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          bash
          actionlint
          coreutils
          curl
          docker-compose
          git
          gnused
          iproute2
          jq
          just
          nixfmt-rfc-style
          OVMF.fd
          openssh
          pre-commit
          python314
          qemu
          shellcheck
          shfmt
          uv
        ];
        shellHook = ''
          export E2E_OVMF_FD_DIR=${pkgs.OVMF.fd}/FV
        '';
      };

      nixosConfigurations = {
        generic-mini-pc = mkHost ./hosts/generic-mini-pc;
        m710q = mkHost ./hosts/m710q;
        e2e-target = mkHost ./hosts/e2e-target;
        rescue-iso = lib.nixosSystem {
          inherit system;
          modules = [ ./rescue/iso.nix ];
        };
        rescue-pxe = lib.nixosSystem {
          inherit system;
          modules = [ ./rescue/pxe.nix ];
        };
      };

      packages.${system} = {
        rescue-iso = self.nixosConfigurations.rescue-iso.config.system.build.isoImage;
        rescue-pxe = pkgs.symlinkJoin {
          name = "nixos-mini-pc-rescue-netboot";
          paths = with self.nixosConfigurations.rescue-pxe.config.system.build; [
            kernel
            netbootRamdisk
            netbootIpxeScript
          ];
        };
        provisioning = pythonProvisioning;
        discover = pythonCommand "discover-hardware" "discover" [
          pkgs.coreutils
          pkgs.jq
          pkgs.openssh
        ];
        select-disk = pythonCommand "select-disk" "select-disk" [ ];
        verify-installed = pythonCommand "verify-installed" "verify-installed" [
          pkgs.coreutils
          pkgs.curl
          pkgs.openssh
        ];
        install = pythonCommand "install" "install" [
          pkgs.coreutils
          pkgs.jq
          pkgs.nix
          pkgs.openssh
        ];
        nixos-anywhere = nixos-anywhere.packages.${system}.default;
        pxe-bundle = pkgs.callPackage ./pxe/bundle.nix {
          rescueConfig = self.nixosConfigurations.rescue-pxe.config;
          revision = self.rev or self.dirtyRev or "unknown";
        };
      };

      apps.${system} = {
        discover = {
          type = "app";
          program = lib.getExe self.packages.${system}.discover;
          meta.description = "Collect read-only remote hardware discovery JSON";
        };
        select-disk = {
          type = "app";
          program = lib.getExe self.packages.${system}.select-disk;
          meta.description = "Select exactly one safe stable disk path";
        };
        install = {
          type = "app";
          program = lib.getExe self.packages.${system}.install;
          meta.description = "Perform confirmed remote installation with nixos-anywhere";
        };
      };

      checks.${system} = {
        generic-system = self.nixosConfigurations.generic-mini-pc.config.system.build.toplevel;
        m710q-system = self.nixosConfigurations.m710q.config.system.build.toplevel;
        disk-layout = pkgs.callPackage ./tests/disk-layout.nix { inherit disko; };
        services = pkgs.callPackage ./tests/services.nix { };
        rescue = pkgs.callPackage ./tests/rescue.nix { };
        shell = pkgs.runCommand "shell-checks" { nativeBuildInputs = [ pkgs.shellcheck ]; } ''
          shellcheck ${./scripts}/*.sh ${./pxe}/build-pxe.sh ${./tests}/*.sh ${./tests/e2e}/*.sh
          touch $out
        '';
        # UV-locked Ruff, Black, pytest, and coverage run in the dedicated CI job.
        # Keeping this flake check to the package build avoids compiling the entire
        # Python 3.14 development-tool closure during unrelated NixOS checks.
        python = pythonProvisioning;
        secrets =
          pkgs.runCommand "secret-helper-tests"
            {
              nativeBuildInputs = [
                pkgs.bash
                pkgs.coreutils
              ];
            }
            ''
              PROJECT_ROOT=${self} bash ${./tests}/secrets.sh
              touch $out
            '';
        compose = pkgs.runCommand "compose-check" { nativeBuildInputs = [ pkgs.docker-compose ]; } ''
          docker-compose -f ${./application/compose.yaml} config --quiet
          touch $out
        '';
        workflows = pkgs.runCommand "workflow-checks" { nativeBuildInputs = [ pkgs.actionlint ]; } ''
          actionlint -no-color ${./.github/workflows}/*.yaml
          touch $out
        '';
      };
    };
}
