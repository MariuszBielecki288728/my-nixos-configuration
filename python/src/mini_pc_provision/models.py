"""Typed views of the stable discovery JSON contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ProvisioningError


@dataclass(frozen=True, slots=True)
class ByIdLink:
    """A stable device link and its resolved kernel-device target."""

    path: str
    target: str


@dataclass(frozen=True, slots=True)
class Disk:
    """The discovery fields used by the fail-closed disk policy."""

    path: str
    size: int
    model: str | None
    serial: str | None
    transport: str | None
    removable: bool
    device_type: str
    mountpoints: tuple[str, ...]

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> Disk:
        """Parse an lsblk object, including mounted descendants."""
        mountpoints: list[str] = []

        def collect(node: dict[str, Any]) -> None:
            mountpoints.extend(item for item in node.get("mountpoints") or [] if item)
            for child in node.get("children") or []:
                collect(child)

        collect(value)
        removable = value.get("rm") in (True, 1, "1")
        return cls(
            path=str(value.get("path", "")),
            size=int(value.get("size") or 0),
            model=value.get("model"),
            serial=value.get("serial"),
            transport=value.get("tran"),
            removable=removable,
            device_type=str(value.get("type", "")),
            mountpoints=tuple(mountpoints),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    """Validated subset of discovery schema version 1.0."""

    raw: dict[str, Any]
    disks: tuple[Disk, ...]
    by_id: tuple[ByIdLink, ...]

    @classmethod
    def from_json(cls, value: Any) -> DiscoveryReport:
        """Validate and parse a discovery report from decoded JSON."""
        if not isinstance(value, dict) or value.get("schema_version") != "1.0":
            raise ProvisioningError("unsupported discovery schema; expected version 1.0")
        devices = value.get("block_devices", {}).get("blockdevices")
        links = value.get("by_id")
        if not isinstance(devices, list) or not isinstance(links, list):
            raise ProvisioningError("discovery report has invalid block-device data")
        try:
            return cls(
                raw=value,
                disks=tuple(Disk.from_json(item) for item in devices),
                by_id=tuple(ByIdLink(str(item["path"]), str(item["target"])) for item in links),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ProvisioningError("discovery report contains malformed device fields") from error
