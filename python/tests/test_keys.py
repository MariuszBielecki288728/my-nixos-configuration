"""SSH provisioning-key policy tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.keys import DEFAULT_KEY_NAME, ensure_default_keypair

PRIVATE_MODE = 0o600
SSH_DIRECTORY_MODE = 0o700


def _ssh_keygen_fixture(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do\n"
        '  if [ "$1" = -f ]; then identity=$2; shift 2; else shift; fi\n'
        "done\n"
        'printf private >"$identity"\n'
        "printf 'ssh-ed25519 QUJDRA== mini-pc-provision\\n' >\"$identity.pub\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_default_keypair_is_created_outside_checkout_and_reused(
    tmp_path: Path, monkeypatch
) -> None:
    """No-argument provisioning creates one dedicated pair in the selected home."""
    tools = tmp_path / "tools"
    tools.mkdir()
    marker = tools / "ssh-keygen"
    _ssh_keygen_fixture(marker)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    home = tmp_path / "home"

    first = ensure_default_keypair(home)
    marker.unlink()
    second = ensure_default_keypair(home)

    expected = home / ".ssh" / DEFAULT_KEY_NAME
    assert first.identity == expected
    assert first.rescue_public == expected.with_suffix(".pub")
    assert second == first
    assert expected.stat().st_mode & 0o777 == PRIVATE_MODE
    assert (home / ".ssh").stat().st_mode & 0o777 == SSH_DIRECTORY_MODE


def test_orphaned_public_key_is_never_overwritten(tmp_path: Path) -> None:
    """An existing public key without its private half requires operator action."""
    ssh_directory = tmp_path / ".ssh"
    ssh_directory.mkdir()
    (ssh_directory / f"{DEFAULT_KEY_NAME}.pub").write_text("existing", encoding="utf-8")
    with pytest.raises(ProvisioningError, match="without its private identity"):
        ensure_default_keypair(tmp_path)
