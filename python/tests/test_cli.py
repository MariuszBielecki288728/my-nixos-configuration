"""CLI tests exercise parsing, files, and output as users invoke them."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mini_pc_provision.cli import main

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_MODE = 0o600


def test_help_documents_commands() -> None:
    """Top-level help exposes every supported provisioning operation."""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "mini_pc_provision.cli", "--help"],
        capture_output=True,
        check=True,
        text=True,
    )
    assert "discover" in completed.stdout
    assert "select-disk" in completed.stdout
    assert "verify-installed" in completed.stdout


def test_select_disk_command_prints_only_path(capsys) -> None:
    """The selector remains safe for command substitution."""
    status = main(["select-disk", str(ROOT / "tests/fixtures/one-disk.json")])
    assert status == 0
    assert capsys.readouterr().out == "/dev/disk/by-id/ata-Safe_SSD_SERIAL\n"


def test_discover_uses_real_subprocess_boundary(tmp_path: Path, monkeypatch, capsys) -> None:
    """A fake executable SSH server verifies transport and report persistence end to end."""
    report = (ROOT / "tests/fixtures/one-disk.json").read_text(encoding="utf-8")
    ssh = tmp_path / "ssh"
    ssh.write_text(f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{report}'\n", encoding="utf-8")
    ssh.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    output = tmp_path / "report.json"
    status = main(["discover", "root@example", "--output", str(output)])
    captured = capsys.readouterr()
    assert status == 0
    assert captured.out == f"{output}\n"
    assert "Safe disk candidates: 1" in captured.err
    assert output.stat().st_mode & 0o777 == PRIVATE_MODE


def test_invalid_report_is_concise(tmp_path: Path, capsys) -> None:
    """Malformed reports produce an actionable error without traceback."""
    report = tmp_path / "bad.json"
    report.write_text("not json", encoding="utf-8")
    assert main(["select-disk", str(report)]) == 1
    assert "not readable JSON" in capsys.readouterr().err
