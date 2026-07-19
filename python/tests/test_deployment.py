"""Deployment policy tests cover confirmation gates and atomic secret rollback."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_pc_provision import deployment
from mini_pc_provision.deployment import (
    DeployOptions,
    RemoteSecretState,
    remote_preflight,
    rollback_remote_secrets,
    stage_remote_secrets,
    validate_deploy_options,
)
from mini_pc_provision.errors import ProvisioningError
from mini_pc_provision.remote import SshConnection
from mini_pc_provision.secrets import SecretBundle

EXPECTED_ROLLBACK_HEALTH_CALLS = 3


class RecordingConnection:
    """Small process-boundary double that never interprets remote shell text."""

    def __init__(self) -> None:
        """Initialize command and copy observations with one existing bot file."""
        self.target = "admin@127.0.0.1"
        self.commands: list[tuple[str, ...]] = []
        self.copies: list[tuple[Path, str]] = []
        self.existing = {"/var/lib/mini-pc/secrets/discord-bot.env"}

    def execute(self, *command: str, input_text: str | None = None) -> str:
        """Return deterministic boundaries for mktemp and existence probes."""
        del input_text
        self.commands.append(command)
        if command[:3] == (
            "mktemp",
            "-d",
            "/tmp/mini-pc-deploy.XXXXXXXX",  # noqa: S108 - exact production fixture.
        ):
            return "/tmp/mini-pc-deploy.ABC123\n"  # noqa: S108 - validated fixture.
        if command[:3] == ("sudo", "test", "-f"):
            if command[3] not in self.existing:
                raise ProvisioningError("missing")
            return ""
        return ""

    def copy_to(self, local_path: Path, remote_path: str) -> None:
        """Record the SCP boundary without copying secret contents elsewhere."""
        self.copies.append((local_path, remote_path))


def secret_file(tmp_path: Path) -> Path:
    """Create a complete Discord bot bootstrap contract."""
    path = tmp_path / "compose.env"
    path.write_text(
        "ACTUAL_PASSWORD=secret\n"
        "ACTUAL_FILE=Budget\n"
        "DISCORD_TOKEN=token\n"
        "DISCORD_BANK_NOTIFICATION_CHANNEL=bank\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_deploy_requires_explicit_admin_target_and_matching_ci_flags(tmp_path: Path) -> None:
    """Noninteractive access never becomes a general production bypass."""
    path = secret_file(tmp_path)
    with pytest.raises(ProvisioningError, match="admin@HOST"):
        validate_deploy_options(
            DeployOptions(SshConnection("root@example"), path, secrets_only=True)
        )
    with pytest.raises(ProvisioningError, match="supplied together"):
        validate_deploy_options(
            DeployOptions(SshConnection("admin@example"), path, secrets_only=True, assume_yes=True)
        )


def test_full_deployment_does_not_require_optional_service_secrets(tmp_path: Path) -> None:
    """A base Actual deployment remains valid when the optional bot is disabled."""
    admin_key = tmp_path / "admin.pub"
    admin_key.write_text("ssh-ed25519 QUJDRA== test\n", encoding="utf-8")
    assert (
        validate_deploy_options(
            DeployOptions(
                SshConnection("admin@example"),
                None,
                host="m710q",
                admin_key_file=admin_key,
            )
        )
        is None
    )


def test_stage_and_rollback_never_put_values_in_remote_arguments(tmp_path: Path) -> None:
    """Secrets cross only the SCP file channel and replacements remain recoverable."""
    connection = RecordingConnection()
    bundle = SecretBundle(
        values={"ACTUAL_PASSWORD": "very-secret"},
        files={"discord-bot.env": "ACTUAL_PASSWORD=very-secret\n"},
    )
    state = stage_remote_secrets(connection, bundle, tmp_path)
    assert state.previous_files == frozenset({"discord-bot.env"})
    assert connection.copies[0][1] == (
        "/tmp/mini-pc-deploy.ABC123/discord-bot.env"  # noqa: S108 - validated fixture.
    )
    assert all(
        "very-secret" not in argument for command in connection.commands for argument in command
    )
    rollback_remote_secrets(connection, state)
    assert any(command[:2] == ("sudo", "cp") for command in connection.commands)


def test_rollback_removes_only_new_contracts() -> None:
    """A failed first-time service secret does not leave a live file behind."""
    connection = RecordingConnection()
    rollback_remote_secrets(
        connection,
        RemoteSecretState(
            "/var/lib/mini-pc/secrets/previous",
            frozenset(),
            frozenset({"discord-bot.env"}),
        ),
    )
    assert connection.commands[-1] == (
        "sudo",
        "rm",
        "-f",
        "--",
        "/var/lib/mini-pc/secrets/discord-bot.env",
    )


def test_remote_preflight_rejects_untrusted_generation_path() -> None:
    """Rollback never executes a path that was not validated as a NixOS closure."""

    class BadGeneration(RecordingConnection):
        def execute(self, *command: str, input_text: str | None = None) -> str:
            del input_text
            if command[:2] == ("readlink", "-f"):
                return "/tmp/not-a-generation\n"  # noqa: S108 - deliberately invalid fixture.
            return ""

    with pytest.raises(ProvisioningError, match="validated store path"):
        remote_preflight(BadGeneration())  # type: ignore[arg-type]


def test_failed_full_activation_restores_generation_and_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Candidate health failure selects the validated old closure and secret copy."""
    old_system = "/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-nixos-system-old-1"
    new_system = "/nix/store/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb-nixos-system-new-2"

    class DeployConnection(RecordingConnection):
        def execute(self, *command: str, input_text: str | None = None) -> str:
            del input_text
            self.commands.append(command)
            if command[:2] == ("readlink", "-f"):
                return f"{old_system}\n"
            if command[:2] == ("free", "--bytes"):
                return "header\nMem: 4294967296 1 1 1 1 1\n"
            if command[:2] == ("df", "--output=avail"):
                return "Avail\n8589934592\n"
            if command[:2] == ("systemctl", "show"):
                return "active\n"
            if command[:4] == ("sudo", "docker", "image", "ls"):
                return "docker.io/example@sha256:none\n"
            if command[:3] == ("sudo", "test", "-f"):
                raise ProvisioningError("missing")
            return ""

    connection = DeployConnection()
    env_file = secret_file(tmp_path)
    admin_key = tmp_path / "admin.pub"
    admin_key.write_text("ssh-ed25519 QUJDRA== test\n", encoding="utf-8")
    state = RemoteSecretState(
        "/var/lib/mini-pc/secrets/previous",
        frozenset({"discord-bot.env"}),
        frozenset({"discord-bot.env"}),
    )
    health_calls = 0

    def health(_connection: object, system_path: str = "/run/current-system") -> None:
        nonlocal health_calls
        health_calls += 1
        if system_path == new_system:
            raise ProvisioningError("candidate is unhealthy")

    monkeypatch.setattr(deployment, "build_system", lambda *_arguments: new_system)
    monkeypatch.setattr(deployment, "copy_system", lambda *_arguments: None)
    monkeypatch.setattr(deployment, "stage_remote_secrets", lambda *_arguments: state)
    monkeypatch.setattr(deployment, "_remote_unit_exists", lambda *_arguments: False)
    monkeypatch.setattr(deployment, "_confirm", lambda *_arguments: None)
    monkeypatch.setattr(deployment, "_health", health)

    with pytest.raises(ProvisioningError, match="prior generation and secrets"):
        deployment.deploy(
            DeployOptions(
                connection=connection,  # type: ignore[arg-type]
                application_env_file=env_file,
                host="e2e-target",
                admin_key_file=admin_key,
            )
        )

    assert health_calls == EXPECTED_ROLLBACK_HEALTH_CALLS
    assert ("sudo", f"{new_system}/bin/switch-to-configuration", "switch") in connection.commands
    assert ("sudo", f"{old_system}/bin/switch-to-configuration", "switch") in connection.commands
    assert (
        "sudo",
        "cp",
        "--preserve=mode,ownership",
        "/var/lib/mini-pc/secrets/previous/discord-bot.env",
        "/var/lib/mini-pc/secrets/discord-bot.env",
    ) in connection.commands
