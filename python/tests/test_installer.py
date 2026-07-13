"""Installer validation tests exercise real temporary files and permissions."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.installer import read_public_key, validate_environment_file


def test_reads_public_key(tmp_path: Path) -> None:
    """A syntactically valid public key is accepted without reading private material."""
    key = tmp_path / "admin.pub"
    key.write_text("ssh-ed25519 QUJDRA== example\n", encoding="utf-8")
    assert read_public_key(key).endswith(" example")


def test_rejects_private_or_empty_key(tmp_path: Path) -> None:
    """Non-public-key input fails before any remote action."""
    key = tmp_path / "bad"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
    with pytest.raises(ProvisioningError, match="public key"):
        read_public_key(key)


def test_environment_file_requires_private_valid_dotenv(tmp_path: Path) -> None:
    """Only a private, regular dotenv file passes secret staging validation."""
    environment = tmp_path / "compose.env"
    environment.write_text("# comment\nTOKEN=value\n", encoding="utf-8")
    environment.chmod(0o600)
    validate_environment_file(environment)
    environment.chmod(0o644)
    with pytest.raises(ProvisioningError, match="0600"):
        validate_environment_file(environment)
    environment.chmod(0o600)
    environment.write_text("not valid\n", encoding="utf-8")
    with pytest.raises(ProvisioningError, match="NAME=value"):
        validate_environment_file(environment)
