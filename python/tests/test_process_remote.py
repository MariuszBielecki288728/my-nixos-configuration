"""Integration tests for local process and OpenSSH argument boundaries."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.process import run
from mini_pc_provision.remote import SshConnection


def test_process_captures_output_and_failure() -> None:
    """Commands run as argument vectors and failures become domain errors."""
    completed = run([sys.executable, "-c", "print('ok')"], capture_output=True)
    assert completed.stdout == "ok\n"
    with pytest.raises(ProvisioningError, match="command failed"):
        run([sys.executable, "-c", "raise SystemExit(4)"], capture_output=True)
    with pytest.raises(ProvisioningError, match="unavailable"):
        run(["command-that-does-not-exist-anywhere"])


def test_ssh_arguments_include_explicit_policy(tmp_path: Path, monkeypatch) -> None:
    """Identity and isolated known-host settings are passed without shell interpolation."""
    identity = tmp_path / "key"
    identity.touch()
    monkeypatch.setenv("SSH_USER_KNOWN_HOSTS_FILE", str(tmp_path / "known_hosts"))
    monkeypatch.setenv("SSH_CONNECT_TIMEOUT", "7")
    arguments = SshConnection("root@example", 2222, identity).arguments()
    assert "ConnectTimeout=7" in arguments
    assert f"UserKnownHostsFile={tmp_path / 'known_hosts'}" in arguments
    assert arguments[-3:] == ["-p", "2222", "root@example"]
    assert ["-i", str(identity)] == arguments[arguments.index("-i") : arguments.index("-i") + 2]


def test_ssh_execute_uses_executable_boundary(tmp_path: Path, monkeypatch) -> None:
    """OpenSSH execution is tested with an executable fixture, not a mocked function."""
    ssh = tmp_path / "ssh"
    ssh.write_text("#!/bin/sh\nprintf remote-ok\n", encoding="utf-8")
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert SshConnection("root@example").execute("true") == "remote-ok"
