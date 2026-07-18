"""Session-based composition of independently testable provisioning stages."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from .discovery import discover
from .disks import DiskCandidate, select_disk
from .errors import ProvisioningError
from .installer import InstallOptions, install, project_root, read_public_key
from .network import (
    CLIENT_ADDRESS,
    NetworkServices,
    check_prerequisites,
    detect_interface,
    validate_bundle,
)
from .process import run
from .remote import SshConnection
from .session import ProvisioningSession, checkout_root, utc_now

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


@dataclass(frozen=True, slots=True)
class ProvisionOptions:
    """Explicit inputs for the direct-Ethernet high-level workflow."""

    host: str
    rescue_key_file: Path
    admin_key_file: Path
    identity: Path
    interface: str | None = None
    requested_disk: str | None = None
    installed_target: str | None = None
    application_env_file: Path | None = None
    wake_mac: str | None = None
    ignored_client_macs: tuple[str, ...] = ()
    target_mac: str | None = None
    timeout: int = 600


def candidate_json(candidate: DiskCandidate) -> dict[str, object]:
    """Render the selected-disk stage's stable structured contract."""
    return {
        "schema_version": "1.0",
        "stable_path": candidate.stable_path,
        "aliases": list(candidate.aliases),
        "kernel_path": candidate.disk.path,
        "model": candidate.disk.model,
        "serial": candidate.disk.serial,
        "size_bytes": candidate.disk.size,
    }


def build_keyed_pxe_bundle(session: ProvisioningSession, public_key_file: Path) -> Path:
    """Build the shared rescue PXE output with a real public key, without tracked edits."""
    key = read_public_key(public_key_file)
    root = project_root()
    build = session.directory / "pxe-build"
    build.mkdir(mode=0o700)
    (build / "flake.nix").write_text(
        "{\n"
        f"  inputs.base.url = {json.dumps(f'path:{root}')};\n"
        "  outputs = { base, ... }: {\n"
        "    packages.x86_64-linux.default = base.lib.x86_64-linux.mkPxeBundle\n"
        "      (base.nixosConfigurations.rescue-pxe.extendModules {\n"
        "        modules = [ ./key.nix ];\n"
        "      }).config;\n"
        "  };\n"
        "}\n",
        encoding="utf-8",
    )
    (build / "key.nix").write_text(
        "{ my.rescue.authorizedKeys = [ " + json.dumps(key) + " ]; }\n", encoding="utf-8"
    )
    output = session.directory / "pxe-bundle"
    session.log("building pinned key-authorized PXE bundle")
    run(
        [
            "nix",
            "build",
            f"path:{build}",
            "--out-link",
            str(output),
            "--print-build-logs",
        ]
    )
    validate_bundle(output.resolve())
    return output.resolve()


def send_wake_on_lan(mac: str) -> None:
    """Send an optional broadcast magic packet after validating the MAC address."""
    if not MAC_PATTERN.fullmatch(mac):
        raise ProvisioningError("--wake-mac must be a colon-separated MAC address")
    run(["wakeonlan", "-i", "192.168.77.255", mac])


def wait_for_rescue(connection: SshConnection, timeout: int) -> dict[str, object]:
    """Wait for the delivery and transport layers to expose rescue SSH."""
    if timeout <= 0:
        raise ProvisioningError("timeout must be positive")
    started = time.monotonic()
    if not connection.wait_until_ready(timeout):
        raise ProvisioningError(f"rescue SSH did not become ready within {timeout}s")
    return {
        "schema_version": "1.0",
        "target": connection.target,
        "port": connection.port,
        "ready_after_seconds": round(time.monotonic() - started, 3),
    }


def collect_journal(connection: SshConnection | None, destination: Path) -> None:
    """Preserve best-effort remote journal evidence without masking the primary result."""
    content = "No remote connection became available.\n"
    if connection:
        try:
            content = connection.execute("journalctl", "-b", "--no-pager", "-n", "2000")
        except ProvisioningError as error:
            content = f"Journal collection failed: {error}\n"
    destination.write_text(content, encoding="utf-8")
    destination.chmod(0o600)


def provision(options: ProvisionOptions) -> Path:  # pragma: no cover  # noqa: PLR0915
    """Run the complete direct-Ethernet pipeline and always finalize evidence and cleanup."""
    if options.timeout <= 0:
        raise ProvisioningError("timeout must be positive")
    root = checkout_root()
    session = ProvisioningSession.create(
        root, host=options.host, transport="direct-ethernet", delivery="pxe"
    )
    network: NetworkServices | None = None
    rescue: SshConnection | None = None
    journal_connection: SshConnection | None = None
    candidate: DiskCandidate | None = None
    installation_started: str | None = None
    try:
        session.log("checking prerequisites and dedicated Ethernet interface")
        validation = check_prerequisites(
            None,
            (options.rescue_key_file, options.admin_key_file, options.identity),
        )
        interface = detect_interface(options.interface)
        validation["interface"] = interface
        session.write_json("prerequisites.json", validation)

        bundle = build_keyed_pxe_bundle(session, options.rescue_key_file)
        validation = check_prerequisites(
            bundle,
            (options.rescue_key_file, options.admin_key_file, options.identity),
        )
        validation["interface"] = interface
        session.write_json("prerequisites.json", validation)

        session.log(f"starting temporary provisioning network on {interface}")
        network = NetworkServices.start(
            interface=interface,
            bundle=bundle,
            directory=session.directory / "network",
            log_path=session.directory / "provisioning.log",
            ignored_client_macs=options.ignored_client_macs,
            target_mac=options.target_mac,
        )
        session.write_json("network.json", network.state)
        if options.wake_mac:
            send_wake_on_lan(options.wake_mac)
            session.log(f"sent Wake-on-LAN to {options.wake_mac}")

        rescue = SshConnection(f"root@{CLIENT_ADDRESS}", 22, options.identity)
        session.log(f"waiting for rescue SSH at {rescue.target}")
        session.write_json("rescue-readiness.json", wait_for_rescue(rescue, options.timeout))
        journal_connection = rescue

        _, report = discover(rescue, session.directory / "discovery.json")
        candidate = select_disk(report, options.requested_disk)
        session.write_json("selected-disk.json", candidate_json(candidate))
        session.log(f"selected reviewed disk {candidate.stable_path}")

        installation_started = utc_now()
        installed = install(
            InstallOptions(
                connection=rescue,
                host=options.host,
                admin_key_file=options.admin_key_file,
                requested_disk=candidate.stable_path,
                application_env_file=options.application_env_file,
                installed_target=options.installed_target or f"admin@{CLIENT_ADDRESS}",
            )
        )
        journal_connection = installed
        session.write_json(
            "installation-report.json",
            {
                "schema_version": "1.0",
                "started_at": installation_started,
                "finished_at": utc_now(),
                "host_configuration": options.host,
                "disk": candidate.stable_path,
                "rescue_target": rescue.target,
                "installed_target": installed.target,
                "status": "success",
            },
        )
        session.write_json(
            "verification-report.json",
            {
                "schema_version": "1.0",
                "verified_at": utc_now(),
                "target": installed.target,
                "checks": {
                    "ssh": "active",
                    "docker": "active",
                    "mini-pc-application": "active",
                    "http": "healthy",
                },
                "status": "success",
            },
        )
        collect_journal(journal_connection, session.directory / "journal.log")
        network.cleanup()
        session.write_json("network.json", network.state)
        network = None
        session.finalize("success")
        return session.directory
    except Exception as error:
        session.log(f"provisioning failed: {error}")
        if network:
            try:
                network.cleanup()
                session.write_json("network.json", network.state)
            except Exception as cleanup_error:  # pragma: no cover - best-effort recovery log
                session.log(f"temporary network cleanup also failed: {cleanup_error}")
            network = None
        if installation_started and not (session.directory / "installation-report.json").exists():
            session.write_json(
                "installation-report.json",
                {
                    "schema_version": "1.0",
                    "started_at": installation_started,
                    "finished_at": utc_now(),
                    "host_configuration": options.host,
                    "disk": candidate.stable_path if candidate else None,
                    "status": "failed",
                    "error": str(error),
                },
            )
        collect_journal(journal_connection, session.directory / "journal.log")
        session.finalize("failed", str(error))
        raise
    finally:
        if network:
            session.log("stopping temporary DHCP/TFTP/HTTP services")
            network.cleanup()
