"""Persistent evidence for one provisioning attempt."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ProvisioningError


def utc_now() -> str:
    """Return a stable UTC timestamp for reports."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def checkout_root() -> Path:
    """Locate the writable checkout used for ignored session artifacts."""
    configured = os.environ.get("PROJECT_CHECKOUT_ROOT")
    candidates = [Path(configured).resolve()] if configured else []
    current = Path.cwd().resolve()
    candidates.extend((current, *current.parents))
    for candidate in candidates:
        if (candidate / ".git").exists() and (candidate / "flake.nix").is_file():
            return candidate
    raise ProvisioningError("run provisioning from a writable Git checkout")


def atomic_json(path: Path, value: Any) -> None:
    """Write private JSON atomically so interrupted stages never leave partial reports."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def git_revision(root: Path) -> tuple[str, bool]:
    """Read commit and dirtiness without changing the checkout."""
    executable = shutil.which("git")
    if not executable:
        raise ProvisioningError("cannot read Git revision: git is unavailable")
    try:
        revision = subprocess.run(  # noqa: S603
            [executable, "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(  # noqa: S603
                [executable, "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProvisioningError("cannot read Git revision for provisioning metadata") from error
    return revision, dirty


@dataclass(slots=True)
class ProvisioningSession:
    """A private artifact directory finalized on both success and failure."""

    directory: Path
    metadata: dict[str, Any]
    started_monotonic: float

    @classmethod
    def create(cls, root: Path, *, host: str, transport: str, delivery: str) -> ProvisioningSession:
        """Create a collision-safe session and its initial metadata."""
        started = utc_now()
        stem = started.replace(":", "-")
        directory = root / "artifacts" / "sessions" / f"{stem}-{os.getpid()}"
        try:
            directory.mkdir(parents=True, mode=0o700)
        except OSError as error:
            raise ProvisioningError(f"cannot create provisioning session: {directory}") from error
        revision, dirty = git_revision(root)
        lock = root / "flake.lock"
        lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest()
        metadata = {
            "schema_version": "1.0",
            "started_at": started,
            "git_commit": revision,
            "git_dirty": dirty,
            "flake_lock_sha256": lock_hash,
            "target_hostname": host,
            "transport_backend": transport,
            "delivery_backend": delivery,
            "result": "running",
        }
        session = cls(directory, metadata, time.monotonic())
        session.write_json("metadata.json", metadata)
        session.write_json(
            "environment.json",
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "wsl": "microsoft" in platform.release().lower(),
            },
        )
        (directory / "provisioning.log").touch(mode=0o600)
        return session

    def write_json(self, name: str, value: Any) -> Path:
        """Persist one structured stage output inside this session."""
        path = self.directory / name
        atomic_json(path, value)
        return path

    def log(self, message: str) -> None:
        """Append a timestamped operator-safe event."""
        with (self.directory / "provisioning.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{utc_now()} {message}\n")

    def finalize(self, result: str, error: str | None = None) -> None:
        """Record terminal status without deleting any evidence."""
        self.metadata.update(
            {
                "finished_at": utc_now(),
                "result": result,
                "total_duration_seconds": round(time.monotonic() - self.started_monotonic, 3),
            }
        )
        if error:
            self.metadata["error"] = error
        self.write_json("metadata.json", self.metadata)
        self.log(f"session finalized: {result}")
