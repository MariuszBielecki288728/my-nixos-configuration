"""Disk-policy tests use realistic discovery JSON rather than mocked objects."""

from __future__ import annotations

import pytest

from mini_pc_provision.disks import (
    safe_candidates,
    select_disk,
    stable_path_priority,
    validate_candidate_unchanged,
)
from mini_pc_provision.errors import ProvisioningError


def test_selects_only_safe_disk(fixture_report) -> None:
    """A single internal unmounted disk resolves to its stable path."""
    selected = select_disk(fixture_report("one-disk.json"))
    assert selected.stable_path == "/dev/disk/by-id/ata-Safe_SSD_SERIAL"


def test_ambiguous_report_requires_explicit_disk(fixture_report) -> None:
    """Multiple safe disks fail closed while a reviewed path is accepted."""
    report = fixture_report("two-disks.json")
    with pytest.raises(ProvisioningError, match="2 safe candidates"):
        select_disk(report)
    assert select_disk(report, "/dev/disk/by-id/nvme-SSD_B").disk.path == "/dev/nvme0n1"


@pytest.mark.parametrize("requested", ["/dev/sda", "/dev/disk/by-id/not-present"])
def test_rejects_unsafe_explicit_paths(fixture_report, requested: str) -> None:
    """Explicit input cannot bypass stable-path or candidate validation."""
    with pytest.raises(ProvisioningError):
        select_disk(fixture_report("one-disk.json"), requested)


def test_mounted_disk_is_excluded(fixture_report) -> None:
    """A mount on the disk or any child excludes the whole disk."""
    assert safe_candidates(fixture_report("mounted-disk.json")) == ()


def test_stable_alias_priority_is_explicit(fixture_report) -> None:
    """WWN wins over NVMe, ATA, SCSI, and lexical ordering."""
    report = fixture_report("one-disk.json")
    report.raw["by_id"].extend(
        [
            {"path": "/dev/disk/by-id/scsi-z", "target": "/dev/sda"},
            {"path": "/dev/disk/by-id/wwn-0x1", "target": "/dev/sda"},
        ]
    )
    reparsed = type(report).from_json(report.raw)
    selected = select_disk(reparsed)
    assert selected.stable_path == "/dev/disk/by-id/wwn-0x1"
    assert selected.aliases == (
        "/dev/disk/by-id/wwn-0x1",
        "/dev/disk/by-id/ata-Safe_SSD_SERIAL",
        "/dev/disk/by-id/scsi-z",
    )
    assert stable_path_priority("/dev/disk/by-id/nvme-eui.123") < stable_path_priority(
        "/dev/disk/by-id/nvme-serial"
    )


def test_explicit_secondary_alias_normalizes_to_preferred(fixture_report) -> None:
    """A reviewed alias is accepted but the strongest stable identity is retained."""
    report = fixture_report("one-disk.json")
    report.raw["by_id"].append({"path": "/dev/disk/by-id/wwn-0x1", "target": "/dev/sda"})
    selected = select_disk(
        type(report).from_json(report.raw), "/dev/disk/by-id/ata-Safe_SSD_SERIAL"
    )
    assert selected.stable_path == "/dev/disk/by-id/wwn-0x1"


def test_revalidation_rejects_identity_or_mount_changes(fixture_report) -> None:
    """The pre-install check fails if immutable identity or mount state changed."""
    original_report = fixture_report("one-disk.json")
    selected = select_disk(original_report)
    validate_candidate_unchanged(selected, fixture_report("one-disk.json"))

    changed = fixture_report("one-disk.json")
    changed.raw["block_devices"]["blockdevices"][0]["serial"] = "REPLACED"
    with pytest.raises(ProvisioningError, match="identity changed"):
        validate_candidate_unchanged(selected, type(changed).from_json(changed.raw))
    with pytest.raises(ProvisioningError, match="no longer present"):
        validate_candidate_unchanged(selected, fixture_report("mounted-disk.json"))
