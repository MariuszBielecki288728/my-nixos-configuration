"""Disk-policy tests use realistic discovery JSON rather than mocked objects."""

from __future__ import annotations

import pytest

from mini_pc_provision.disks import safe_candidates, select_disk
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
