"""Temporary, isolated direct-Ethernet DHCP/TFTP/HTTP system adapter."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ProvisioningError
from .process import run

SERVER_ADDRESS = "192.168.77.1"
CLIENT_ADDRESS = "192.168.77.2"
PREFIX = "24"
HTTP_PORT = 8081
INTERFACE_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]{1,15}$")
MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
VIRTUAL_PREFIXES = ("br-", "docker", "veth", "virbr", "tap", "tun", "wg")
MIN_SS_FIELDS = 4


def validate_ignored_client_macs(macs: tuple[str, ...]) -> tuple[str, ...]:
    """Validate and normalize runtime-only DHCP client exclusions."""
    invalid = [mac for mac in macs if not MAC_PATTERN.fullmatch(mac)]
    if invalid:
        raise ProvisioningError(
            "--ignore-client-mac must be a colon-separated MAC address: " + ", ".join(invalid)
        )
    return tuple(dict.fromkeys(mac.lower() for mac in macs))


def choose_interface(
    links: list[dict[str, Any]],
    default_interfaces: set[str],
    physical_interfaces: set[str],
    requested: str | None = None,
) -> str:
    """Select exactly one unused physical Ethernet interface, or validate one explicitly."""
    by_name = {str(item.get("ifname", "")): item for item in links}

    def eligible(name: str) -> bool:
        item = by_name.get(name, {})
        return bool(
            name
            and name != "lo"
            and item.get("link_type") == "ether"
            and name not in default_interfaces
            and name in physical_interfaces
            and not name.startswith(VIRTUAL_PREFIXES)
        )

    if requested:
        if not INTERFACE_PATTERN.fullmatch(requested) or not eligible(requested):
            raise ProvisioningError(
                "requested interface is not a dedicated physical Ethernet device "
                "without the default route"
            )
        return requested
    candidates = sorted(name for name in by_name if eligible(name))
    if len(candidates) != 1:
        raise ProvisioningError(
            f"expected exactly one dedicated physical Ethernet interface, found {len(candidates)}; "
            "use --interface after reviewing host networking"
        )
    return candidates[0]


def detect_interface(requested: str | None = None) -> str:
    """Inspect Linux networking and apply the fail-closed interface policy."""
    links = json.loads(run(["ip", "-json", "link", "show"], capture_output=True).stdout)
    routes = json.loads(
        run(["ip", "-json", "route", "show", "default"], capture_output=True).stdout
    )
    defaults = {str(route.get("dev")) for route in routes if route.get("dev")}
    physical = {
        item.name
        for item in Path("/sys/class/net").iterdir()
        if (item / "device").exists() and not (item / "wireless").exists()
    }
    return choose_interface(links, defaults, physical, requested)


def check_no_dhcp_listener() -> None:
    """Refuse to compete with a local DHCP server."""
    listeners = run(["ss", "-H", "-lunp"], capture_output=True).stdout
    for line in listeners.splitlines():
        fields = line.split()
        endpoint = fields[3] if len(fields) >= MIN_SS_FIELDS else ""
        if endpoint.endswith(":67"):
            raise ProvisioningError(f"a DHCP server is already listening on UDP 67: {line}")


def validate_bundle(bundle: Path) -> None:
    """Require the complete generated TFTP and HTTP roots."""
    required = (
        bundle / "tftp/ipxe.efi",
        bundle / "http/nixos/bzImage",
        bundle / "http/nixos/initrd",
        bundle / "http/nixos/boot.ipxe",
        bundle / "boot-manifest.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ProvisioningError("PXE bundle is incomplete: " + ", ".join(missing))


def check_prerequisites(bundle: Path | None, key_files: tuple[Path, ...]) -> dict[str, Any]:
    """Return a structured prerequisite report or fail before host networking changes."""
    commands = ("dnsmasq", "ip", "ss", "nix", "ssh", sys.executable)
    missing = [command for command in commands if not shutil.which(command)]
    if missing:
        raise ProvisioningError("required commands are unavailable: " + ", ".join(missing))
    unreadable = [str(path) for path in key_files if not path.is_file()]
    if unreadable:
        raise ProvisioningError("required SSH key files are unreadable: " + ", ".join(unreadable))
    if bundle is not None:
        validate_bundle(bundle)
    return {
        "schema_version": "1.0",
        "commands": list(commands),
        "bundle": str(bundle) if bundle else None,
        "keys": [str(path) for path in key_files],
        "status": "ready",
    }


@dataclass(slots=True)
class NetworkServices:
    """Recorded temporary service state, also usable by a later cleanup command."""

    state_path: Path
    state: dict[str, Any]
    _processes: tuple[subprocess.Popen[str], ...] = field(default_factory=tuple, repr=False)

    @classmethod
    def start(  # noqa: PLR0912, PLR0915
        cls,
        *,
        interface: str,
        bundle: Path,
        directory: Path,
        log_path: Path,
        ignored_client_macs: tuple[str, ...] = (),
    ) -> NetworkServices:
        """Assign the isolated address and start dnsmasq plus the local HTTP server."""
        if os.geteuid() != 0:
            raise ProvisioningError("temporary DHCP/TFTP requires root; rerun with sudo")
        ignored_client_macs = validate_ignored_client_macs(ignored_client_macs)
        validate_bundle(bundle)
        check_no_dhcp_listener()
        addresses = json.loads(
            run(["ip", "-json", "address", "show", "dev", interface], capture_output=True).stdout
        )
        global_ipv4 = [
            address.get("local")
            for item in addresses
            for address in item.get("addr_info", [])
            if address.get("family") == "inet" and address.get("scope") == "global"
        ]
        unexpected = [address for address in global_ipv4 if address != SERVER_ADDRESS]
        if unexpected:
            raise ProvisioningError(
                f"dedicated interface {interface} already has global IPv4: {unexpected}"
            )
        was_up = bool(addresses and "UP" in addresses[0].get("flags", []))
        address_added = SERVER_ADDRESS not in global_ipv4
        directory.mkdir(parents=True, exist_ok=True)
        config = directory / "dnsmasq.conf"
        config.write_text(
            "\n".join(
                [
                    "port=0",
                    f"interface={interface}",
                    "bind-interfaces",
                    "log-dhcp",
                    *(f"dhcp-host={mac},ignore" for mac in ignored_client_macs),
                    f"dhcp-range={CLIENT_ADDRESS},{CLIENT_ADDRESS},255.255.255.0,1h",
                    f"dhcp-option=3,{SERVER_ADDRESS}",
                    f"dhcp-option=6,{SERVER_ADDRESS}",
                    # Keep lease state in memory. The session is deliberately mode
                    # 0700, while dnsmasq drops privileges after binding.
                    "dhcp-leasefile=",
                    "dhcp-match=set:efi64,option:client-arch,7",
                    "dhcp-match=set:efi64,option:client-arch,9",
                    f"dhcp-boot=tag:efi64,ipxe.efi,,{SERVER_ADDRESS}",
                    "dhcp-userclass=set:ipxe,iPXE",
                    f"dhcp-boot=tag:ipxe,http://{SERVER_ADDRESS}:{HTTP_PORT}/nixos/boot.ipxe",
                    "enable-tftp",
                    f"tftp-root={bundle / 'tftp'}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        if not was_up:
            run(["ip", "link", "set", "dev", interface, "up"])
        if address_added:
            run(["ip", "address", "add", f"{SERVER_ADDRESS}/{PREFIX}", "dev", interface])
        dnsmasq: subprocess.Popen[str] | None = None
        http: subprocess.Popen[str] | None = None
        try:
            log_stream = log_path.open("a", encoding="utf-8")
            dnsmasq_executable = shutil.which("dnsmasq")
            if not dnsmasq_executable:
                raise ProvisioningError("required command is unavailable: dnsmasq")
            try:
                dnsmasq = subprocess.Popen(  # noqa: S603
                    [dnsmasq_executable, "--keep-in-foreground", f"--conf-file={config}"],
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                http = subprocess.Popen(  # noqa: S603
                    [
                        sys.executable,
                        "-m",
                        "http.server",
                        str(HTTP_PORT),
                        "--bind",
                        SERVER_ADDRESS,
                        "--directory",
                        str(bundle / "http"),
                    ],
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            finally:
                log_stream.close()
        except Exception:
            for process in (http, dnsmasq):
                if process and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)
            if address_added:
                run(
                    ["ip", "address", "del", f"{SERVER_ADDRESS}/{PREFIX}", "dev", interface],
                    check=False,
                )
            if not was_up:
                run(["ip", "link", "set", "dev", interface, "down"], check=False)
            raise
        if dnsmasq is None or http is None:  # pragma: no cover - guarded above
            raise ProvisioningError("temporary service process creation failed")
        state = {
            "schema_version": "1.0",
            "interface": interface,
            "server_address": SERVER_ADDRESS,
            "client_address": CLIENT_ADDRESS,
            "http_port": HTTP_PORT,
            "ignored_client_macs": list(ignored_client_macs),
            "address_added": address_added,
            "interface_was_up": was_up,
            "dnsmasq_pid": dnsmasq.pid,
            "http_pid": http.pid,
            "dnsmasq_marker": str(config),
            "http_marker": str(bundle / "http"),
        }
        state_path = directory / "network-state.json"
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        state_path.chmod(0o600)
        instance = cls(state_path, state, (http, dnsmasq))
        time.sleep(1)
        if dnsmasq.poll() is not None or http.poll() is not None:
            instance.cleanup()
            raise ProvisioningError("temporary DHCP/TFTP/HTTP service failed to start; inspect log")
        return instance

    @classmethod
    def load(cls, state_path: Path) -> NetworkServices:
        """Load state produced by a standalone start stage."""
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProvisioningError(f"network state is unreadable: {state_path}") from error
        return cls(state_path, state)

    def cleanup(self) -> None:
        """Stop only recorded matching processes and restore owned interface state."""
        stopped: list[tuple[int, str]] = []
        for role in ("http", "dnsmasq"):
            pid = int(self.state.get(f"{role}_pid", 0))
            marker = str(self.state.get(f"{role}_marker", ""))
            command_path = Path(f"/proc/{pid}/cmdline")
            try:
                command = command_path.read_bytes().replace(b"\0", b" ").decode()
            except OSError:
                continue
            if marker and marker in command:
                os.kill(pid, signal.SIGTERM)
                stopped.append((pid, marker))
        for process in self._processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        stopped = [item for item in stopped if Path(f"/proc/{item[0]}").exists()]
        deadline = time.monotonic() + 3
        while stopped and time.monotonic() < deadline:
            stopped = [item for item in stopped if Path(f"/proc/{item[0]}").exists()]
            if stopped:
                time.sleep(0.05)
        for pid, marker in stopped:
            try:
                command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
                if marker in command:
                    os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        interface = str(self.state.get("interface", ""))
        if self.state.get("address_added") and INTERFACE_PATTERN.fullmatch(interface):
            run(
                ["ip", "address", "del", f"{SERVER_ADDRESS}/{PREFIX}", "dev", interface],
                check=False,
            )
        if not self.state.get("interface_was_up") and INTERFACE_PATTERN.fullmatch(interface):
            run(["ip", "link", "set", "dev", interface, "down"], check=False)
        self.state["cleaned"] = True
        self.state_path.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
