"""Pure, fail-closed disk selection policy."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ProvisioningError
from .models import DiscoveryReport, Disk

SUPPORTED_TRANSPORTS = frozenset({"sata", "nvme", "sas", "scsi", "virtio"})


@dataclass(frozen=True, slots=True)
class DiskCandidate:
    """An internal whole disk paired with its preferred stable path."""

    disk: Disk
    stable_path: str


def safe_candidates(report: DiscoveryReport) -> tuple[DiskCandidate, ...]:
    """Return disks satisfying every safety rule, without touching any device."""
    candidates: list[DiskCandidate] = []
    for disk in report.disks:
        stable_paths = sorted(link.path for link in report.by_id if link.target == disk.path)
        stable_path = stable_paths[0] if stable_paths else None
        transport_supported = disk.transport in SUPPORTED_TRANSPORTS or (
            disk.transport in (None, "") and stable_path is not None and "/virtio-" in stable_path
        )
        if (
            disk.device_type == "disk"
            and not disk.removable
            and disk.transport != "usb"
            and not disk.mountpoints
            and stable_path is not None
            and transport_supported
        ):
            candidates.append(DiskCandidate(disk, stable_path))
    return tuple(candidates)


def select_disk(report: DiscoveryReport, requested: str | None = None) -> DiskCandidate:
    """Select exactly one safe disk or validate one explicitly reviewed by-id path."""
    candidates = safe_candidates(report)
    if requested is not None:
        if not requested.startswith("/dev/disk/by-id/"):
            raise ProvisioningError("--disk must use /dev/disk/by-id/...")
        matches = [candidate for candidate in candidates if candidate.stable_path == requested]
        if len(matches) != 1:
            raise ProvisioningError(
                f"explicit disk is absent or fails the safety policy: {requested}"
            )
        return matches[0]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ProvisioningError(
            "no safe internal disk candidate remains; review discovery before continuing"
        )
    raise ProvisioningError(
        f"{len(candidates)} safe candidates remain; rerun with --disk and a reviewed "
        "full by-id path"
    )
