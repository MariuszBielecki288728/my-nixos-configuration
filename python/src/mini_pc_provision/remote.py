"""OpenSSH transport with one consistent, explicit safety policy."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from .process import run


@dataclass(frozen=True, slots=True)
class SshConnection:
    """Connection settings shared by discovery, installation, and verification."""

    target: str
    port: int = 22
    identity: Path | None = None

    def arguments(self) -> list[str]:
        """Build OpenSSH arguments without invoking a shell."""
        timeout = os.environ.get("SSH_CONNECT_TIMEOUT", "10")
        arguments = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={timeout}",
            "-o",
            "ServerAliveInterval=5",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        known_hosts = os.environ.get("SSH_USER_KNOWN_HOSTS_FILE")
        if known_hosts:
            arguments.extend(["-o", f"UserKnownHostsFile={known_hosts}"])
        if self.identity:
            arguments.extend(["-i", str(self.identity), "-o", "IdentitiesOnly=yes"])
        return [*arguments, "-p", str(self.port), self.target]

    def execute(self, *remote_command: str, input_text: str | None = None) -> str:
        """Execute a remote command and return stdout."""
        completed = run(
            [*self.arguments(), *remote_command],
            capture_output=True,
            input_text=input_text,
        )
        return completed.stdout

    def wait_until_ready(self, timeout: int) -> bool:
        """Poll SSH until it responds or the monotonic deadline expires."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.execute("true")
                return True
            except Exception:
                time.sleep(2)
        return False
