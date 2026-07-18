"""Pure network policy and generated-bundle validation tests."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.network import (
    NetworkServices,
    check_no_dhcp_listener,
    check_prerequisites,
    choose_interface,
    validate_bundle,
)

LINKS = [
    {"ifname": "lo", "link_type": "loopback"},
    {"ifname": "eth0", "link_type": "ether"},
    {"ifname": "enp3s0", "link_type": "ether"},
    {"ifname": "docker0", "link_type": "ether"},
]


def test_interface_policy_excludes_default_and_virtual_devices() -> None:
    """The one unused physical Ethernet NIC is selected deterministically."""
    assert choose_interface(LINKS, {"eth0"}, {"eth0", "enp3s0"}) == "enp3s0"
    assert choose_interface(LINKS, {"eth0"}, {"eth0", "enp3s0"}, "enp3s0") == "enp3s0"


def test_interface_policy_fails_closed_on_ambiguity_or_default_route() -> None:
    """Explicit input cannot claim Wi-Fi, virtual devices, or the Internet route."""
    with pytest.raises(ProvisioningError, match="exactly one"):
        choose_interface(LINKS, set(), {"eth0", "enp3s0"})
    with pytest.raises(ProvisioningError, match="dedicated physical"):
        choose_interface(LINKS, {"eth0"}, {"eth0", "enp3s0"}, "eth0")
    with pytest.raises(ProvisioningError, match="dedicated physical"):
        choose_interface(LINKS, set(), {"docker0"}, "docker0")


def test_bundle_contract_requires_tftp_http_and_manifest(tmp_path: Path) -> None:
    """A partial legacy HTTP tree cannot start the temporary server."""
    with pytest.raises(ProvisioningError, match="incomplete"):
        validate_bundle(tmp_path)
    for relative in (
        "tftp/ipxe.efi",
        "http/nixos/bzImage",
        "http/nixos/initrd",
        "http/nixos/boot.ipxe",
        "boot-manifest.json",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    validate_bundle(tmp_path)


def executable(path: Path, body: str) -> Path:
    """Create one executable process fixture."""
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def complete_bundle(root: Path) -> Path:
    """Create the generated bundle shape without large boot artifacts."""
    for relative in (
        "tftp/ipxe.efi",
        "http/nixos/bzImage",
        "http/nixos/initrd",
        "http/nixos/boot.ipxe",
        "boot-manifest.json",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return root


def test_prerequisite_and_dhcp_checks_use_executable_boundaries(
    tmp_path: Path, monkeypatch
) -> None:
    """Missing keys and active UDP 67 listeners fail before any network mutation."""
    for name in ("dnsmasq", "ip", "nix", "ssh"):
        executable(tmp_path / name, "exit 0")
    executable(tmp_path / "ss", "printf '%s\\n' 'UNCONN 0 0 0.0.0.0:67 0.0.0.0:*'")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    key = tmp_path / "key"
    key.touch()
    report = check_prerequisites(complete_bundle(tmp_path / "bundle"), (key,))
    assert report["status"] == "ready"
    with pytest.raises(ProvisioningError, match="UDP 67"):
        check_no_dhcp_listener()
    with pytest.raises(ProvisioningError, match="unreadable"):
        check_prerequisites(None, (tmp_path / "missing",))


def test_temporary_services_record_and_cleanup_owned_state(tmp_path: Path, monkeypatch) -> None:
    """Process fixtures exercise start/load/cleanup without touching a real interface."""
    bundle = complete_bundle(tmp_path / "bundle")
    executable(
        tmp_path / "ip",
        'if [ "$1 $2 $3" = "-json address show" ]; then '
        "printf '%s' '[{\"flags\":[],\"addr_info\":[]}]'; fi",
    )
    executable(tmp_path / "ss", "exit 0")
    sleeper = "trap 'exit 0' TERM; while :; do /bin/sleep 1; done"
    executable(tmp_path / "dnsmasq", sleeper)
    fake_python = executable(tmp_path / "python-fixture", sleeper)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr("mini_pc_provision.network.os.geteuid", lambda: 0)
    monkeypatch.setattr("mini_pc_provision.network.sys.executable", str(fake_python))
    directory = tmp_path / "state"
    services = NetworkServices.start(
        interface="enp3s0",
        bundle=bundle,
        directory=directory,
        log_path=tmp_path / "services.log",
        ignored_client_macs=("02:00:00:00:00:01", "02:00:00:00:00:01"),
    )
    assert services.state["address_added"] is True
    assert services.state["ignored_client_macs"] == ["02:00:00:00:00:01"]
    config = (directory / "dnsmasq.conf").read_text(encoding="utf-8")
    assert config.count("dhcp-host=02:00:00:00:00:01,ignore") == 1
    assert NetworkServices.load(services.state_path).state["interface"] == "enp3s0"
    services.cleanup()
    assert services.state["cleaned"] is True
    time.sleep(0.05)
    with pytest.raises(ProvisioningError, match="unreadable"):
        NetworkServices.load(tmp_path / "missing.json")


def test_temporary_services_require_root(tmp_path: Path, monkeypatch) -> None:
    """Starting DHCP/TFTP as an unprivileged operator fails before any mutation."""
    monkeypatch.setattr("mini_pc_provision.network.os.geteuid", lambda: 1000)
    with pytest.raises(ProvisioningError, match="requires root"):
        NetworkServices.start(
            interface="enp3s0",
            bundle=tmp_path / "bundle",
            directory=tmp_path / "state",
            log_path=tmp_path / "services.log",
        )


def test_temporary_services_reject_invalid_ignored_mac(tmp_path: Path, monkeypatch) -> None:
    """Unvalidated client identifiers never reach the generated dnsmasq config."""
    monkeypatch.setattr("mini_pc_provision.network.os.geteuid", lambda: 0)
    with pytest.raises(ProvisioningError, match="ignore-client-mac"):
        NetworkServices.start(
            interface="enp3s0",
            bundle=tmp_path / "bundle",
            directory=tmp_path / "state",
            log_path=tmp_path / "services.log",
            ignored_client_macs=("not-a-mac",),
        )
