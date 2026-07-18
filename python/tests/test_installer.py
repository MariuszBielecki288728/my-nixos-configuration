"""Installer validation tests exercise real temporary files and permissions."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_pc_provision.disks import select_disk
from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.installer import (
    InstallOptions,
    installed_target_candidates,
    read_public_key,
    validate_ci_disposable,
    validate_environment_file,
)
from mini_pc_provision.remote import SshConnection


def test_reads_public_key(tmp_path: Path) -> None:
    """A syntactically valid public key is accepted without reading private material."""
    key = tmp_path / "admin.pub"
    key.write_text("ssh-ed25519 QUJDRA== example\n", encoding="utf-8")
    assert read_public_key(key).endswith(" example")


def test_rejects_private_or_empty_key(tmp_path: Path) -> None:
    """Non-public-key input fails before any remote action."""
    key = tmp_path / "bad"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
    with pytest.raises(ProvisioningError, match="public key"):
        read_public_key(key)


def test_environment_file_requires_private_valid_dotenv(tmp_path: Path) -> None:
    """Only a private, regular dotenv file passes secret staging validation."""
    environment = tmp_path / "compose.env"
    environment.write_text("# comment\nTOKEN=value\n", encoding="utf-8")
    environment.chmod(0o600)
    validate_environment_file(environment)
    environment.chmod(0o644)
    with pytest.raises(ProvisioningError, match="0600"):
        validate_environment_file(environment)
    environment.chmod(0o600)
    environment.write_text("not valid\n", encoding="utf-8")
    with pytest.raises(ProvisioningError, match="NAME=value"):
        validate_environment_file(environment)


def test_ci_bypass_requires_environment_qemu_host_and_disk(fixture_report, tmp_path: Path) -> None:
    """No individual flag can make a physical discovery noninteractive."""
    report = fixture_report("one-disk.json")
    report.raw["dmi"] = {"vendor": "QEMU", "product_name": "Standard PC (Q35)"}
    disk = report.raw["block_devices"]["blockdevices"][0]
    disk.update({"path": "/dev/vda", "serial": "nixos-e2e", "tran": "virtio"})
    report.raw["by_id"][0] = {
        "path": "/dev/disk/by-id/virtio-nixos-e2e",
        "target": "/dev/vda",
    }
    report = type(report).from_json(report.raw)
    options = InstallOptions(
        SshConnection("root@rescue"), "e2e-target", tmp_path / "admin.pub", assume_yes=True
    )
    validate_ci_disposable(options, report, select_disk(report), {"CI": "true"})
    with pytest.raises(ProvisioningError, match="CI environment"):
        validate_ci_disposable(options, report, select_disk(report), {})
    with pytest.raises(ProvisioningError, match="host configuration"):
        validate_ci_disposable(
            InstallOptions(SshConnection("root@rescue"), "m710q", tmp_path / "admin.pub"),
            report,
            select_disk(report),
            {"CI": "true"},
        )


def test_installed_target_fallback_order(fixture_report, tmp_path: Path) -> None:
    """Explicit target precedes mDNS and the prior global rescue address."""
    report = fixture_report("one-disk.json")
    report.raw["network_interfaces"] = [
        {
            "ifname": "enp1s0",
            "addr_info": [{"family": "inet", "scope": "global", "local": "192.168.77.2"}],
        }
    ]
    options = InstallOptions(
        SshConnection("root@rescue", 2222, tmp_path / "key"),
        "m710q",
        tmp_path / "admin.pub",
        installed_target="admin@installed.example",
    )
    targets = [item.target for item in installed_target_candidates(options, report)]
    assert targets == ["admin@installed.example", "admin@m710q.local", "admin@192.168.77.2"]
