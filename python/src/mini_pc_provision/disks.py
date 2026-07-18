"""Pure, fail-closed disk selection policy."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ProvisioningError
from .models import DiscoveryReport, Disk

SUPPORTED_TRANSPORTS = frozenset({"sata", "nvme", "sas", "scsi", "virtio"})


def stable_path_priority(path: str) -> tuple[int, str]:
    """Rank whole-disk aliases explicitly instead of trusting directory ordering."""
    name = path.rsplit("/", maxsplit=1)[-1].lower()
    if name.startswith("wwn-"):
        rank = 0
    elif name.startswith("nvme-eui.") or name.startswith("nvme-eui-"):
        rank = 1
    elif name.startswith("nvme-"):
        rank = 2
    elif name.startswith("ata-"):
        rank = 3
    elif name.startswith("scsi-"):
        rank = 4
    elif name.startswith("virtio-"):
        # Virtio aliases exist only for supported disposable test targets.
        rank = 5
    else:
        rank = 6
    return rank, path


@dataclass(frozen=True, slots=True)
class DiskCandidate:
    """An internal whole disk paired with its preferred stable path."""

    disk: Disk
    stable_path: str
    aliases: tuple[str, ...]


def safe_candidates(report: DiscoveryReport) -> tuple[DiskCandidate, ...]:
    """Return disks satisfying every safety rule, without touching any device."""
    candidates: list[DiskCandidate] = []
    for disk in report.disks:
        stable_paths = sorted(
            (link.path for link in report.by_id if link.target == disk.path),
            key=stable_path_priority,
        )
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
            candidates.append(DiskCandidate(disk, stable_path, tuple(stable_paths)))
    return tuple(candidates)


def select_disk(report: DiscoveryReport, requested: str | None = None) -> DiskCandidate:
    """Select exactly one safe disk or validate one explicitly reviewed by-id path."""
    candidates = safe_candidates(report)
    if requested is not None:
        if not requested.startswith("/dev/disk/by-id/"):
            raise ProvisioningError("--disk must use /dev/disk/by-id/...")
        matches = [candidate for candidate in candidates if requested in candidate.aliases]
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


def validate_candidate_unchanged(
    selected: DiskCandidate, current_report: DiscoveryReport
) -> DiskCandidate:
    """Revalidate the complete selected-disk identity against a fresh discovery."""
    try:
        current = select_disk(current_report, selected.stable_path)
    except ProvisioningError as error:
        raise ProvisioningError(
            "selected disk is no longer present, stable, unmounted, and safe"
        ) from error
    expected_identity = (
        selected.disk.path,
        selected.disk.model,
        selected.disk.serial,
        selected.disk.size,
        selected.aliases,
    )
    current_identity = (
        current.disk.path,
        current.disk.model,
        current.disk.serial,
        current.disk.size,
        current.aliases,
    )
    if current_identity != expected_identity:
        raise ProvisioningError(
            "selected disk identity changed after confirmation; refusing installation"
        )
    return current
