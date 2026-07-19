"""Runtime secret contracts remain strict and service-scoped."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.secrets import load_secret_bundle


def private_dotenv(tmp_path: Path, contents: str) -> Path:
    """Create the attended-bootstrap file shape accepted by production code."""
    path = tmp_path / "compose.env"
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_renders_exact_discord_service_contract(tmp_path: Path) -> None:
    """The optional bot receives only its supported variables."""
    bundle = load_secret_bundle(
        private_dotenv(
            tmp_path,
            "ACTUAL_PASSWORD=shared-secret\n"
            "DISCORD_TOKEN=token\n"
            "DISCORD_BANK_NOTIFICATION_CHANNEL=bank\n"
            "DISCORD_RECEIPT_CHANNEL=receipts\n"
            "ACTUAL_FILE=Budget\n",
        )
    )
    assert set(bundle.files) == {"discord-bot.env"}
    assert "DISCORD_RECEIPT_CHANNEL=receipts" in bundle.files["discord-bot.env"]
    assert "ACTUAL_PASSWORD=shared-secret" in bundle.files["discord-bot.env"]


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("UNKNOWN=value\n", "unsupported key"),
        ("ACTUAL_PASSWORD=value\n", "no complete service contract"),
        (
            "ACTUAL_PASSWORD=one\nACTUAL_PASSWORD=two\n"
            "DISCORD_TOKEN=token\nDISCORD_BANK_NOTIFICATION_CHANNEL=bank\n"
            "ACTUAL_FILE=Budget\n",
            "duplicate key",
        ),
        ("# only a comment\n", "no complete service contract"),
    ],
)
def test_rejects_ambiguous_or_incomplete_contracts(
    tmp_path: Path, contents: str, message: str
) -> None:
    """Misspellings and partial secret rotations fail before any SSH call."""
    with pytest.raises(ProvisioningError, match=message):
        load_secret_bundle(private_dotenv(tmp_path, contents))
