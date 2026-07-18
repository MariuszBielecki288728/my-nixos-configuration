"""Creation and selection of host-side SSH credentials."""

from __future__ import annotations

import os
import pwd
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ProvisioningError
from .process import run

DEFAULT_KEY_NAME = "mini_pc_provision_ed25519"
USER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*[$]?$")
PRIVATE_MODE = 0o600
SSH_DIRECTORY_MODE = 0o700


@dataclass(frozen=True, slots=True)
class ProvisioningKeys:
    """Resolved private identity and public keys for rescue and installed access."""

    rescue_public: Path
    admin_public: Path
    identity: Path


def invoking_user_home() -> Path:
    """Return the original user's home when provisioning is invoked through sudo."""
    sudo_user = os.environ.get("SUDO_USER")
    if os.geteuid() == 0 and sudo_user and sudo_user != "root":
        if not USER_PATTERN.fullmatch(sudo_user):
            raise ProvisioningError("SUDO_USER is not a valid local account name")
        try:
            return Path(pwd.getpwnam(sudo_user).pw_dir)
        except KeyError as error:
            raise ProvisioningError(
                f"SUDO_USER does not identify a local account: {sudo_user}"
            ) from error
    return Path.home()


def ensure_default_keypair(home: Path | None = None) -> ProvisioningKeys:
    """Create or reuse a dedicated Ed25519 key pair outside the project checkout."""
    ssh_directory = (home or invoking_user_home()) / ".ssh"
    identity = ssh_directory / DEFAULT_KEY_NAME
    public_key = identity.with_suffix(".pub")
    ssh_directory.mkdir(mode=SSH_DIRECTORY_MODE, parents=True, exist_ok=True)
    ssh_directory.chmod(SSH_DIRECTORY_MODE)

    if public_key.exists() and not identity.is_file():
        raise ProvisioningError(
            f"public key exists without its private identity: {public_key}; "
            "restore the private key or remove the orphaned public key"
        )
    if not identity.exists():
        run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "mini-pc-provision",
                "-f",
                str(identity),
            ]
        )
    if not identity.is_file() or not public_key.is_file():
        raise ProvisioningError("ssh-keygen did not create the expected provisioning key pair")
    identity.chmod(PRIVATE_MODE)
    return ProvisioningKeys(public_key, public_key, identity)


def resolve_provisioning_keys(
    rescue_public: Path | None,
    admin_public: Path | None,
    identity: Path | None,
) -> ProvisioningKeys:
    """Generate defaults when no key flags are supplied, otherwise require a complete set."""
    supplied = (rescue_public, admin_public, identity)
    if not any(supplied):
        return ensure_default_keypair()
    if rescue_public is None or admin_public is None or identity is None:
        raise ProvisioningError(
            "supply --rescue-key-file, --admin-key-file, and --identity together, "
            "or omit all three to create a dedicated key automatically"
        )
    return ProvisioningKeys(
        rescue_public.expanduser(),
        admin_public.expanduser(),
        identity.expanduser(),
    )
