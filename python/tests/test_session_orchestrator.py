"""Provisioning session evidence and pure stage-output tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mini_pc_provision.disks import select_disk
from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.orchestrator import (
    build_keyed_pxe_bundle,
    candidate_json,
    collect_journal,
    reset_known_hosts,
    send_wake_on_lan,
    wait_for_rescue,
)
from mini_pc_provision.remote import SshConnection
from mini_pc_provision.session import ProvisioningSession, atomic_json

PRIVATE_MODE = 0o600


def test_reset_known_hosts_is_private_and_removes_prior_identity(tmp_path: Path) -> None:
    """Rescue and installed systems use separate TOFU boundaries at the fixed address."""
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("stale rescue identity\n", encoding="utf-8")
    reset_known_hosts(known_hosts)
    assert known_hosts.read_text(encoding="utf-8") == ""
    assert known_hosts.stat().st_mode & 0o777 == PRIVATE_MODE


def test_atomic_json_is_private_and_complete(tmp_path: Path) -> None:
    """Stage reports are mode 0600 and never expose a temporary partial file."""
    output = tmp_path / "report.json"
    atomic_json(output, {"status": "ready"})
    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "ready"}
    assert output.stat().st_mode & 0o777 == PRIVATE_MODE
    assert not (tmp_path / ".report.json.tmp").exists()


def test_session_finalizes_failure_without_removing_evidence(tmp_path: Path, monkeypatch) -> None:
    """Metadata and logs survive a failed attempt with duration and error."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "flake.nix").touch()
    (tmp_path / "flake.lock").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("mini_pc_provision.session.git_revision", lambda _root: ("abc", True))
    session = ProvisioningSession.create(
        tmp_path, host="m710q", transport="direct-ethernet", delivery="pxe"
    )
    session.log("stage started")
    session.finalize("failed", "expected test failure")
    metadata = json.loads((session.directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["result"] == "failed"
    assert metadata["error"] == "expected test failure"
    assert metadata["total_duration_seconds"] >= 0
    assert "stage started" in (session.directory / "provisioning.log").read_text(encoding="utf-8")


def test_selected_disk_stage_contains_all_aliases(fixture_report) -> None:
    """Structured selection reports preserve identity for later revalidation."""
    value = candidate_json(select_disk(fixture_report("one-disk.json")))
    assert value["stable_path"] == "/dev/disk/by-id/ata-Safe_SSD_SERIAL"
    assert value["aliases"] == ["/dev/disk/by-id/ata-Safe_SSD_SERIAL"]
    assert value["serial"] == "SERIAL"


def test_wake_on_lan_rejects_unvalidated_input() -> None:
    """An invalid MAC never reaches the external command boundary."""
    with pytest.raises(ProvisioningError, match="MAC"):
        send_wake_on_lan("not-a-mac")


def test_build_bundle_and_rescue_stages_use_process_fixtures(tmp_path: Path, monkeypatch) -> None:
    """Build, readiness, journal, and Wake-on-LAN boundaries run through real executables."""
    root = tmp_path / "repository"
    root.mkdir()
    (root / "flake.nix").touch()
    monkeypatch.setenv("PROJECT_ROOT", str(root))
    tools = tmp_path / "tools"
    tools.mkdir()
    nix = tools / "nix"
    nix.write_text(
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do\n"
        '  if [ "$1" = --out-link ]; then out=$2; shift 2; else shift; fi\n'
        "done\n"
        'mkdir -p "$out/tftp" "$out/http/nixos"\n'
        'touch "$out/tftp/ipxe.efi" "$out/http/nixos/bzImage" '
        '"$out/http/nixos/initrd" "$out/http/nixos/boot.ipxe" '
        '"$out/boot-manifest.json"\n',
        encoding="utf-8",
    )
    nix.chmod(0o755)
    ssh = tools / "ssh"
    ssh.write_text(
        '#!/bin/sh\ncase "$*" in *journalctl*) printf journal-ok;; *) exit 0;; esac\n',
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    wake = tools / "wakeonlan"
    wake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    key = tmp_path / "rescue.pub"
    key.write_text("ssh-ed25519 QUJDRA== test\n", encoding="utf-8")
    session = ProvisioningSession(tmp_path / "session", {}, 0.0)
    session.directory.mkdir()
    (session.directory / "provisioning.log").touch()
    bundle = build_keyed_pxe_bundle(session, key)
    assert (bundle / "tftp/ipxe.efi").is_file()
    connection = SshConnection("root@example")
    assert wait_for_rescue(connection, 1)["target"] == "root@example"
    journal = tmp_path / "journal.log"
    collect_journal(connection, journal)
    assert journal.read_text(encoding="utf-8") == "journal-ok"
    send_wake_on_lan("00:11:22:33:44:55")
