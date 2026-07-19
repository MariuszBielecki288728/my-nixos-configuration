"""Documented command-line interface for safe provisioning operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .deployment import DeployOptions, deploy
from .discovery import candidate_summary, discover
from .disks import select_disk
from .errors import ProvisioningError
from .installer import InstallOptions, install, verify_installed
from .keys import resolve_provisioning_keys
from .models import DiscoveryReport
from .network import NetworkServices, check_prerequisites, detect_interface
from .orchestrator import ProvisionOptions, provision, wait_for_rescue
from .remote import SshConnection

MAX_PORT = 65_535


def connection_from(arguments: argparse.Namespace) -> SshConnection:
    """Create validated SSH settings from common CLI options."""
    if not 1 <= arguments.port <= MAX_PORT:
        raise ProvisioningError("port must be between 1 and 65535")
    identity = Path(arguments.identity).expanduser() if arguments.identity else None
    if identity and not identity.is_file():
        raise ProvisioningError(f"identity file is not readable: {identity}")
    return SshConnection(arguments.target, arguments.port, identity)


def add_connection_options(parser: argparse.ArgumentParser, *, positional: bool) -> None:
    """Add consistent SSH arguments to a subcommand parser."""
    if positional:
        parser.add_argument("target", metavar="USER@HOST", help="SSH destination")
    else:
        parser.add_argument("--target", required=True, metavar="USER@HOST", help="SSH destination")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--identity", metavar="FILE", help="private SSH identity on this PC")


def add_deploy_command(commands: argparse._SubParsersAction) -> None:
    """Add the complete and secret-only installed-host deployment manual."""
    deploy_parser = commands.add_parser(
        "deploy",
        help="deploy a complete NixOS generation or rotate only application secrets",
        description=(
            "Preflight an installed host, preserve administrator access, stage root-only "
            "secrets, activate and health-check a locally built generation, and restore the "
            "prior generation and secrets if activation fails."
        ),
    )
    add_connection_options(deploy_parser, positional=False)
    deploy_parser.add_argument("--host", help="flake NixOS configuration (full mode)")
    deploy_parser.add_argument(
        "--admin-key-file", type=Path, help="OpenSSH public key preserved in full mode"
    )
    deploy_parser.add_argument(
        "--application-env-file",
        type=Path,
        help="private mode-0600 source dotenv file (required for --secrets-only)",
    )
    deploy_parser.add_argument(
        "--secrets-only",
        action="store_true",
        help="rotate service secret files without building or activating NixOS",
    )
    deploy_parser.add_argument(
        "--yes", action="store_true", help="bypass confirmation (requires --ci-disposable)"
    )
    deploy_parser.add_argument(
        "--ci-disposable",
        action="store_true",
        help="declare a localhost target to be a disposable CI VM",
    )


def build_parser() -> argparse.ArgumentParser:  # noqa: PLR0915 - one documented parser tree.
    """Build the complete parser; argparse supplies detailed per-command manuals."""
    parser = argparse.ArgumentParser(
        prog="mini-pc-provision",
        description="Readable, fail-closed NixOS mini-PC provisioning tools.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    discover_parser = commands.add_parser(
        "discover",
        help="collect a read-only hardware report over SSH",
        description=(
            "Collect DMI, lsblk/by-id, mounts, interfaces, PCI, and USB data. "
            "The remote collector performs no writes."
        ),
    )
    add_connection_options(discover_parser, positional=True)
    discover_parser.add_argument("--output", type=Path, help="report destination")

    select_parser = commands.add_parser(
        "select-disk",
        help="apply the fail-closed disk policy to a report",
        description=(
            "Select only when exactly one non-removable, unmounted, supported whole disk "
            "has a stable by-id path. This command never accesses a block device."
        ),
    )
    select_parser.add_argument("report", type=Path, help="discovery JSON file")
    select_parser.add_argument("--disk", help="explicit reviewed /dev/disk/by-id path")

    install_parser = commands.add_parser(
        "install",
        help="perform a confirmed remote installation",
        description=(
            "Verify rescue SSH, discover and select a safe disk, require exact confirmation, "
            "run pinned nixos-anywhere/disko, reboot, and verify services."
        ),
    )
    add_connection_options(install_parser, positional=False)
    install_parser.add_argument("--host", required=True, help="flake NixOS configuration")
    install_parser.add_argument(
        "--admin-key-file", required=True, type=Path, help="OpenSSH public key for admin"
    )
    install_parser.add_argument("--disk", help="reviewed /dev/disk/by-id whole-disk path")
    install_parser.add_argument(
        "--application-env-file", type=Path, help="private mode-0600 Compose dotenv file"
    )
    install_parser.add_argument(
        "--installed-target",
        metavar="admin@HOST",
        help="preferred installed SSH target before mDNS and discovered-IP fallbacks",
    )
    install_parser.add_argument(
        "--yes", action="store_true", help="bypass confirmation (requires --ci-disposable)"
    )
    install_parser.add_argument(
        "--ci-disposable", action="store_true", help="declare the target a disposable CI disk"
    )

    verify_parser = commands.add_parser(
        "verify-installed",
        help="wait for installed-system services and HTTP health",
    )
    add_connection_options(verify_parser, positional=False)
    verify_parser.add_argument("--timeout", type=int, default=300, help="readiness timeout")

    add_deploy_command(commands)

    prerequisite_parser = commands.add_parser(
        "check-prerequisites",
        help="validate local binaries, keys, and an optional generated PXE bundle",
    )
    prerequisite_parser.add_argument("--bundle", type=Path, help="generated PXE bundle")
    prerequisite_parser.add_argument(
        "--key-file", action="append", default=[], type=Path, help="required readable key file"
    )

    network_parser = commands.add_parser(
        "start-provisioning-network",
        help="start temporary direct-Ethernet DHCP, TFTP, and HTTP services",
    )
    network_parser.add_argument("--bundle", required=True, type=Path)
    network_parser.add_argument("--directory", required=True, type=Path)
    network_parser.add_argument("--interface")
    network_parser.add_argument("--log", type=Path)
    network_parser.add_argument(
        "--ignore-client-mac",
        action="append",
        default=[],
        help="MAC to exclude from DHCP (repeatable; useful for a bridged host adapter)",
    )
    network_parser.add_argument(
        "--target-mac", help="target MAC to reserve the fixed provisioning address for"
    )

    wait_parser = commands.add_parser("wait-for-rescue", help="wait until rescue SSH is reachable")
    add_connection_options(wait_parser, positional=False)
    wait_parser.add_argument("--timeout", type=int, default=600)

    cleanup_parser = commands.add_parser(
        "cleanup", help="stop a recorded temporary provisioning network"
    )
    cleanup_parser.add_argument("state", type=Path, help="network-state.json from the start stage")

    provision_parser = commands.add_parser(
        "provision",
        help="run the complete session-based direct-Ethernet provisioning pipeline",
    )
    provision_parser.add_argument("--host", default="m710q", help="flake host configuration")
    provision_parser.add_argument(
        "--rescue-key-file",
        type=Path,
        help="rescue public key (omit all key flags to create a dedicated pair)",
    )
    provision_parser.add_argument(
        "--admin-key-file",
        type=Path,
        help="installed admin public key (omit all key flags to create a dedicated pair)",
    )
    provision_parser.add_argument(
        "--identity",
        type=Path,
        help="private SSH identity (omit all key flags to create a dedicated pair)",
    )
    provision_parser.add_argument("--interface", help="reviewed dedicated Ethernet interface")
    provision_parser.add_argument("--disk", help="reviewed stable whole-disk path")
    provision_parser.add_argument("--installed-target", metavar="admin@HOST")
    provision_parser.add_argument("--application-env-file", type=Path)
    provision_parser.add_argument("--wake-mac", help="optional target MAC for Wake-on-LAN")
    provision_parser.add_argument(
        "--ignore-client-mac",
        action="append",
        default=[],
        help="MAC to exclude from DHCP (repeatable; useful for a bridged host adapter)",
    )
    provision_parser.add_argument(
        "--target-mac", help="target MAC to reserve the fixed provisioning address for"
    )
    provision_parser.add_argument("--timeout", type=int, default=600)
    return parser


def execute(arguments: argparse.Namespace) -> None:
    """Dispatch one parsed command."""
    if arguments.command == "discover":
        path, report = discover(connection_from(arguments), arguments.output)
        print(f"Discovery report: {path}", file=sys.stderr)
        print(candidate_summary(report), file=sys.stderr)
        print(path)
    elif arguments.command == "select-disk":
        try:
            decoded = json.loads(arguments.report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProvisioningError(
                f"discovery report is not readable JSON: {arguments.report}"
            ) from error
        print(select_disk(DiscoveryReport.from_json(decoded), arguments.disk).stable_path)
    elif arguments.command == "install":
        install(
            InstallOptions(
                connection=connection_from(arguments),
                host=arguments.host,
                admin_key_file=arguments.admin_key_file.expanduser(),
                requested_disk=arguments.disk,
                application_env_file=(
                    arguments.application_env_file.expanduser()
                    if arguments.application_env_file
                    else None
                ),
                installed_target=arguments.installed_target,
                assume_yes=arguments.yes,
                ci_disposable=arguments.ci_disposable,
            )
        )
    elif arguments.command == "verify-installed":
        if arguments.timeout <= 0:
            raise ProvisioningError("timeout must be positive")
        verify_installed(connection_from(arguments), arguments.timeout)
    elif arguments.command == "deploy":
        deploy(
            DeployOptions(
                connection=connection_from(arguments),
                host=arguments.host,
                admin_key_file=(
                    arguments.admin_key_file.expanduser() if arguments.admin_key_file else None
                ),
                application_env_file=(
                    arguments.application_env_file.expanduser()
                    if arguments.application_env_file
                    else None
                ),
                secrets_only=arguments.secrets_only,
                assume_yes=arguments.yes,
                ci_disposable=arguments.ci_disposable,
            )
        )
    elif arguments.command == "check-prerequisites":
        bundle = arguments.bundle.expanduser().resolve() if arguments.bundle else None
        keys = tuple(path.expanduser() for path in arguments.key_file)
        print(json.dumps(check_prerequisites(bundle, keys), indent=2))
    elif arguments.command == "start-provisioning-network":
        directory = arguments.directory.expanduser().resolve()
        interface = detect_interface(arguments.interface)
        network = NetworkServices.start(
            interface=interface,
            bundle=arguments.bundle.expanduser().resolve(),
            directory=directory,
            log_path=(arguments.log or directory / "provisioning.log").expanduser().resolve(),
            ignored_client_macs=tuple(arguments.ignore_client_mac),
            target_mac=arguments.target_mac,
        )
        print(network.state_path)
    elif arguments.command == "wait-for-rescue":
        print(json.dumps(wait_for_rescue(connection_from(arguments), arguments.timeout), indent=2))
    elif arguments.command == "cleanup":
        NetworkServices.load(arguments.state.expanduser().resolve()).cleanup()
    elif arguments.command == "provision":
        keys = resolve_provisioning_keys(
            arguments.rescue_key_file, arguments.admin_key_file, arguments.identity
        )
        session = provision(
            ProvisionOptions(
                host=arguments.host,
                rescue_key_file=keys.rescue_public,
                admin_key_file=keys.admin_public,
                identity=keys.identity,
                interface=arguments.interface,
                requested_disk=arguments.disk,
                installed_target=arguments.installed_target,
                application_env_file=(
                    arguments.application_env_file.expanduser()
                    if arguments.application_env_file
                    else None
                ),
                wake_mac=arguments.wake_mac,
                ignored_client_macs=tuple(arguments.ignore_client_mac),
                target_mac=arguments.target_mac,
                timeout=arguments.timeout,
            )
        )
        print(session)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and render domain errors without a Python traceback."""
    try:
        execute(build_parser().parse_args(argv))
    except ProvisioningError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
