"""Strict runtime-secret parsing and per-service rendering outside the Nix store."""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .errors import ProvisioningError

ENVIRONMENT_LINE = re.compile(r"^(?:#.*|\s*|[A-Za-z_][A-Za-z0-9_]*=.*)$")
NAME_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

ACTUAL_AI_KEYS = frozenset(
    {
        "ACTUAL_PASSWORD",
        "ACTUAL_BUDGET_ID",
        "ACTUAL_E2E_PASSWORD",
    }
)
ACTUAL_AI_REQUIRED = frozenset({"ACTUAL_PASSWORD", "ACTUAL_BUDGET_ID"})
DISCORD_BOT_KEYS = frozenset(
    {
        "DISCORD_TOKEN",
        "DISCORD_BANK_NOTIFICATION_CHANNEL",
        "DISCORD_RECEIPT_CHANNEL",
        "ACTUAL_PASSWORD",
        "ACTUAL_FILE",
        "ACTUAL_ENCRYPTION_PASSWORD",
        "ACTUAL_ACCOUNT",
    }
)
DISCORD_BOT_REQUIRED = frozenset(
    {
        "DISCORD_TOKEN",
        "DISCORD_BANK_NOTIFICATION_CHANNEL",
        "ACTUAL_PASSWORD",
        "ACTUAL_FILE",
    }
)
KNOWN_KEYS = ACTUAL_AI_KEYS | DISCORD_BOT_KEYS


@dataclass(frozen=True, slots=True)
class SecretBundle:
    """Validated secret values rendered only to the services that consume them."""

    values: dict[str, str]
    files: dict[str, str]


def _render(values: dict[str, str], keys: frozenset[str]) -> str:
    """Render selected values deterministically without normalizing their contents."""
    return "".join(f"{name}={values[name]}\n" for name in sorted(keys & values.keys()))


def load_secret_bundle(path: Path) -> SecretBundle:
    """Validate a private dotenv file and split complete service-specific contracts."""
    try:
        details = path.stat()
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ProvisioningError(f"application environment file is not readable: {path}") from error
    if not stat.S_ISREG(details.st_mode):
        raise ProvisioningError(f"application environment file is not a regular file: {path}")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise ProvisioningError("application environment file must have mode 0600 or stricter")

    values: dict[str, str] = {}
    for line in lines:
        if not ENVIRONMENT_LINE.fullmatch(line):
            raise ProvisioningError(
                "application environment file must contain only NAME=value lines, "
                "comments, or blanks"
            )
        match = NAME_VALUE.fullmatch(line)
        if not match:
            continue
        name, value = match.groups()
        if name not in KNOWN_KEYS:
            raise ProvisioningError(
                f"application environment file contains unsupported key: {name}"
            )
        if name in values:
            raise ProvisioningError(f"application environment file contains duplicate key: {name}")
        values[name] = value

    files: dict[str, str] = {}
    for filename, allowed, required, triggers in (
        (
            "actual-ai.env",
            ACTUAL_AI_KEYS,
            ACTUAL_AI_REQUIRED,
            ACTUAL_AI_KEYS - {"ACTUAL_PASSWORD"},
        ),
        (
            "discord-bot.env",
            DISCORD_BOT_KEYS,
            DISCORD_BOT_REQUIRED,
            DISCORD_BOT_KEYS - {"ACTUAL_PASSWORD", "ACTUAL_ENCRYPTION_PASSWORD", "ACTUAL_ACCOUNT"},
        ),
    ):
        present = triggers & values.keys()
        if not present:
            continue
        missing = required - values.keys()
        empty = {name for name in required if not values.get(name)}
        if missing or empty:
            count = len(missing | empty)
            raise ProvisioningError(
                f"{filename} secret contract is incomplete ({count} required value(s) missing)"
            )
        files[filename] = _render(values, allowed)
    if not files:
        raise ProvisioningError(
            "application environment file contains no complete service contract"
        )
    return SecretBundle(values=values, files=files)
