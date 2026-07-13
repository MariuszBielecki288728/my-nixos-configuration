"""Read-only remote hardware discovery and report persistence."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .disks import safe_candidates
from .errors import ProvisioningError
from .models import DiscoveryReport
from .remote import SshConnection

REMOTE_COLLECTOR = r"""set -Eeuo pipefail
read_optional() { [[ -r "$1" ]] && tr -d '\n' <"$1" || true; }
by_id=$(find /dev/disk/by-id -maxdepth 1 -type l -printf '%p\n' 2>/dev/null | while IFS= read -r link; do
  jq -n --arg path "$link" --arg target "$(readlink -f -- "$link")" '{path:$path,target:$target}'
done | jq -s '.')
jq -n \
  --arg schema_version "1.0" \
  --arg collected_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg hostname "$(hostname)" \
  --arg vendor "$(read_optional /sys/class/dmi/id/sys_vendor)" \
  --arg product_name "$(read_optional /sys/class/dmi/id/product_name)" \
  --arg product_version "$(read_optional /sys/class/dmi/id/product_version)" \
  --argjson block_devices "$(lsblk --json --bytes --output NAME,PATH,SIZE,MODEL,SERIAL,TRAN,RM,ROTA,TYPE,FSTYPE,MOUNTPOINTS)" \
  --argjson by_id "$by_id" \
  --argjson interfaces "$(ip -json address)" \
  --arg mounts "$(findmnt --json --bytes 2>/dev/null || printf '{\"filesystems\":[]}')" \
  --arg pci "$(lspci -nn 2>/dev/null || true)" \
  --arg usb "$(lsusb 2>/dev/null || true)" \
  '{schema_version:$schema_version,collected_at:$collected_at,hostname:$hostname,
    dmi:{vendor:$vendor,product_name:$product_name,product_version:$product_version},
    block_devices:$block_devices,by_id:$by_id,network_interfaces:$interfaces,
    mounts:($mounts|fromjson),pci_devices:($pci|split("\n")|map(select(length>0))),
    usb_devices:($usb|split("\n")|map(select(length>0)))}'
"""


def default_report_path(target: str) -> Path:
    """Return a timestamped, filesystem-safe discovery artifact path."""
    safe_target = re.sub(r"[^a-zA-Z0-9._-]", "_", target.replace("@", "_"))
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("artifacts/discovery") / f"{timestamp}-{safe_target}.json"


def discover(connection: SshConnection, output: Path | None = None) -> tuple[Path, DiscoveryReport]:
    """Collect, validate, and atomically persist a mode-0600 hardware report."""
    destination = output or default_report_path(connection.target)
    try:
        decoded = json.loads(connection.execute("bash", "-s", input_text=REMOTE_COLLECTOR))
    except json.JSONDecodeError as error:
        raise ProvisioningError("remote discovery returned invalid JSON") from error
    report = DiscoveryReport.from_json(decoded)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(json.dumps(decoded, indent=2) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination, report


def candidate_summary(report: DiscoveryReport) -> str:
    """Format safe candidates for human review on stderr."""
    candidates = safe_candidates(report)
    lines = [f"Safe disk candidates: {len(candidates)}"]
    lines.extend(
        f"  {item.stable_path} | {item.disk.model or 'unknown'} | {item.disk.size} bytes"
        for item in candidates
    )
    return "\n".join(lines)
