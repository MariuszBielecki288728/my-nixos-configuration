"""Rollback-safe deployment of NixOS generations and runtime application secrets."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .errors import ProvisioningError
from .installer import HOST_PATTERN, project_root, read_public_key
from .process import run
from .remote import SshConnection
from .secrets import SecretBundle, load_secret_bundle

STORE_PATH = re.compile(r"^/nix/store/[a-z0-9]{32}-nixos-system-[A-Za-z0-9+._?-]+$")
REMOTE_TEMP = re.compile(r"^/tmp/mini-pc-deploy\.[A-Za-z0-9]+$")
SECRET_FILENAME = re.compile(r"^[a-z0-9-]+\.env$")
MIN_TABULAR_LINES = 2
DEPLOY_TARGET = re.compile(r"^admin@(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])$")
MINIMUM_ROOT_AVAILABLE_BYTES = 2 * 1024**3
MINIMUM_MEMORY_BYTES = 1024**3


@dataclass(frozen=True, slots=True)
class DeployOptions:
    """Operator inputs for a complete or secret-only deployment."""

    connection: SshConnection
    application_env_file: Path | None
    host: str | None = None
    admin_key_file: Path | None = None
    secrets_only: bool = False
    assume_yes: bool = False
    ci_disposable: bool = False


@dataclass(frozen=True, slots=True)
class RemoteSecretState:
    """Remote rollback data for one atomically staged secret set."""

    rollback_directory: str
    previous_files: frozenset[str]
    installed_files: frozenset[str]


def validate_deploy_options(options: DeployOptions) -> SecretBundle | None:
    """Fail before SSH when deployment inputs are incomplete or unsafe."""
    if not DEPLOY_TARGET.fullmatch(options.connection.target):
        raise ProvisioningError("deployment target must be an explicit, valid admin@HOST")
    if options.assume_yes != options.ci_disposable:
        raise ProvisioningError("--yes and --ci-disposable must be supplied together")
    if options.ci_disposable:
        host = options.connection.target.partition("@")[2]
        if os.environ.get("CI", "").lower() not in {"1", "true"} or host not in {
            "127.0.0.1",
            "localhost",
            "[::1]",
        }:
            raise ProvisioningError("noninteractive deployment is limited to localhost in CI")
    if options.secrets_only:
        if options.host or options.admin_key_file:
            raise ProvisioningError("--secrets-only does not accept --host or --admin-key-file")
        if options.application_env_file is None:
            raise ProvisioningError("--secrets-only requires --application-env-file")
    else:
        if not options.host or not HOST_PATTERN.fullmatch(options.host):
            raise ProvisioningError("full deployment requires a valid --host configuration")
        if options.admin_key_file is None:
            raise ProvisioningError("full deployment requires --admin-key-file")
        read_public_key(options.admin_key_file)
    if options.application_env_file is None:
        return None
    return load_secret_bundle(options.application_env_file)


def remote_preflight(connection: SshConnection) -> dict[str, object]:
    """Collect a read-only, non-secret deployment snapshot."""
    connection.execute("true")
    generation = connection.execute("readlink", "-f", "/run/current-system").strip()
    if not STORE_PATH.fullmatch(generation):
        raise ProvisioningError("remote current NixOS generation is not a validated store path")
    memory = connection.execute("free", "--bytes").strip().splitlines()
    disk = connection.execute("df", "--output=avail", "--block-size=1", "/").strip().splitlines()
    if len(memory) < MIN_TABULAR_LINES or len(disk) < MIN_TABULAR_LINES:
        raise ProvisioningError("remote preflight returned incomplete memory or disk information")
    available = int(disk[-1].strip())
    memory_bytes = int(memory[1].split()[1])
    if available < MINIMUM_ROOT_AVAILABLE_BYTES:
        raise ProvisioningError("remote root filesystem has less than 2 GiB available")
    if memory_bytes < MINIMUM_MEMORY_BYTES:
        raise ProvisioningError("remote host has less than 1 GiB of memory")
    return {
        "generation": generation,
        "root_available_bytes": available,
        "memory": " ".join(memory[1].split()[:3]),
        "docker": connection.execute(
            "systemctl", "show", "--property=ActiveState", "--value", "docker"
        ).strip(),
        "application": connection.execute(
            "systemctl", "show", "--property=ActiveState", "--value", "mini-pc-application"
        ).strip(),
        "loaded_images": connection.execute(
            "sudo", "docker", "image", "ls", "--digests", "--format", "{{.Repository}}@{{.Digest}}"
        ).splitlines(),
    }


def _write_runtime_flake(directory: Path, host: str, admin_key: str, root: Path) -> None:
    """Create an untracked flake that preserves the selected administrator key."""
    (directory / "flake.nix").write_text(
        "{\n"
        f"  inputs.base.url = {json.dumps(f'path:{root}')};\n"
        "  outputs = { base, ... }: {\n"
        f'    nixosConfigurations."{host}" = base.nixosConfigurations."{host}".extendModules {{\n'
        "      modules = [ ./runtime.nix ];\n"
        "    };\n"
        "  };\n"
        "}\n",
        encoding="utf-8",
    )
    (directory / "runtime.nix").write_text(
        "{\n" f"  my.ssh.authorizedKeys = [ {json.dumps(admin_key)} ];\n" "}\n",
        encoding="utf-8",
    )


def build_system(host: str, admin_key_file: Path) -> str:
    """Build a key-preserving target generation locally and return its store path."""
    root = project_root()
    admin_key = read_public_key(admin_key_file)
    with tempfile.TemporaryDirectory(prefix="mini-pc-deploy-flake-") as name:
        temporary = Path(name)
        _write_runtime_flake(temporary, host, admin_key, root)
        completed = run(
            [
                "nix",
                "build",
                "--no-link",
                "--print-out-paths",
                f"path:{temporary}#nixosConfigurations.{host}.config.system.build.toplevel",
            ],
            capture_output=True,
        )
    paths = completed.stdout.splitlines()
    if len(paths) != 1 or not STORE_PATH.fullmatch(paths[0]):
        raise ProvisioningError("Nix build did not return exactly one validated system path")
    return paths[0]


def copy_system(connection: SshConnection, system_path: str) -> None:
    """Copy an unsigned local closure through the target's passwordless sudo boundary."""
    environment = os.environ.copy()
    environment["NIX_SSHOPTS"] = connection.shell_escaped_transport_options()
    run(
        [
            "nix",
            "copy",
            "--no-check-sigs",
            "--to",
            f"ssh://{connection.target}?remote-program=sudo%20nix-store",
            system_path,
        ],
        env=environment,
    )


def _remote_file_exists(connection: SshConnection, path: str) -> bool:
    try:
        connection.execute("sudo", "test", "-f", path)
    except ProvisioningError:
        return False
    return True


def _remote_unit_exists(connection: SshConnection, unit: str) -> bool:
    try:
        connection.execute("systemctl", "cat", unit)
    except ProvisioningError:
        return False
    return True


def stage_remote_secrets(
    connection: SshConnection, bundle: SecretBundle, local_directory: Path
) -> RemoteSecretState:
    """Copy per-service files privately and atomically install root-owned replacements."""
    remote_directory = connection.execute(
        "mktemp",
        "-d",
        "/tmp/mini-pc-deploy.XXXXXXXX",  # noqa: S108 - mktemp creates this safely remotely.
    ).strip()
    if not REMOTE_TEMP.fullmatch(remote_directory):
        raise ProvisioningError("remote mktemp returned an unexpected path")
    rollback = "/var/lib/mini-pc/secrets/previous"
    destination_root = "/var/lib/mini-pc/secrets"
    previous: set[str] = set()
    installed: set[str] = set()
    state = RemoteSecretState(rollback, frozenset(), frozenset())
    try:
        connection.execute(
            "sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700", destination_root
        )
        connection.execute(
            "sudo", "install", "-d", "-o", "root", "-g", "root", "-m", "0700", rollback
        )
        for filename, contents in bundle.files.items():
            if not SECRET_FILENAME.fullmatch(filename):
                raise ProvisioningError("internal secret filename failed validation")
            local = local_directory / filename
            local.write_text(contents, encoding="utf-8")
            local.chmod(0o600)
            remote = f"{remote_directory}/{filename}"
            destination = f"{destination_root}/{filename}"
            previous_path = f"{rollback}/{filename}"
            connection.copy_to(local, remote)
            if _remote_file_exists(connection, destination):
                connection.execute(
                    "sudo", "cp", "--preserve=mode,ownership", destination, previous_path
                )
                previous.add(filename)
            else:
                with suppress(ProvisioningError):
                    connection.execute("sudo", "rm", "-f", "--", previous_path)
            connection.execute(
                "sudo",
                "install",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0600",
                remote,
                f"{destination}.new",
            )
            connection.execute("sudo", "mv", "-f", f"{destination}.new", destination)
            installed.add(filename)
            state = RemoteSecretState(rollback, frozenset(previous), frozenset(installed))
    except ProvisioningError:
        rollback_remote_secrets(connection, state)
        raise
    finally:
        connection.execute("rm", "-rf", "--", remote_directory)
    return state


def rollback_remote_secrets(connection: SshConnection, state: RemoteSecretState) -> None:
    """Restore the exact previous files, removing only newly introduced contracts."""
    for filename in state.installed_files:
        destination = f"/var/lib/mini-pc/secrets/{filename}"
        if filename in state.previous_files:
            connection.execute(
                "sudo",
                "cp",
                "--preserve=mode,ownership",
                f"{state.rollback_directory}/{filename}",
                destination,
            )
        else:
            connection.execute("sudo", "rm", "-f", "--", destination)


def _restart_secret_consumers(connection: SshConnection, filenames: frozenset[str]) -> None:
    units = []
    if "discord-bot.env" in filenames:
        units.append("mini-pc-discord-bot.service")
    enabled_units = [unit for unit in units if _remote_unit_exists(connection, unit)]
    if enabled_units:
        connection.execute("sudo", "systemctl", "try-restart", *enabled_units)
        print(f"Restarted {', '.join(enabled_units)}", file=os.sys.stderr)
    else:
        print("No enabled optional service consumes the staged contract", file=os.sys.stderr)


def _health(connection: SshConnection, system_path: str = "/run/current-system") -> None:
    health = f"{system_path}/sw/bin/mini-pc-application-health"
    if _remote_file_exists(connection, health):
        connection.execute("sudo", health)
    else:
        connection.execute("systemctl", "is-active", "--quiet", "sshd", "docker")


def _confirm(options: DeployOptions, summary: str) -> None:
    print(summary, file=os.sys.stderr)
    if options.assume_yes:
        print("CI disposable deployment confirmation bypass is active", file=os.sys.stderr)
        return
    confirmation = input(f"Type {options.connection.target} to activate: ")
    if confirmation != options.connection.target:
        raise ProvisioningError("confirmation did not exactly match the deployment target")


def deploy(options: DeployOptions) -> None:
    """Deploy secrets alone or activate a complete rollback-safe NixOS generation."""
    bundle = validate_deploy_options(options)
    preflight = remote_preflight(options.connection)
    _health(options.connection)
    print(json.dumps(preflight, indent=2), file=os.sys.stderr)
    if options.secrets_only:
        if bundle is None:  # Defensive after validation.
            raise ProvisioningError("secret-only deployment inputs unexpectedly became unavailable")
        _confirm(options, "SECRET-ONLY DEPLOYMENT: no NixOS generation will be activated")
        with tempfile.TemporaryDirectory(prefix="mini-pc-secrets-") as name:
            state = stage_remote_secrets(options.connection, bundle, Path(name))
        try:
            _restart_secret_consumers(options.connection, state.installed_files)
            _health(options.connection)
        except ProvisioningError as error:
            rollback_remote_secrets(options.connection, state)
            _restart_secret_consumers(options.connection, state.installed_files)
            raise ProvisioningError(
                "secret rotation failed health checks; prior files restored"
            ) from error
        print("Secret-only deployment is healthy", file=os.sys.stderr)
        return

    if options.host is None or options.admin_key_file is None:  # Defensive after validation.
        raise ProvisioningError("full deployment inputs unexpectedly became unavailable")
    new_system = build_system(options.host, options.admin_key_file)
    copy_system(options.connection, new_system)
    image_loader = f"{new_system}/sw/bin/mini-pc-load-images"
    if _remote_file_exists(options.connection, image_loader):
        options.connection.execute("sudo", image_loader)
    _confirm(
        options,
        "FULL NIXOS DEPLOYMENT\n"
        f"  Target: {options.connection.target}\n"
        f"  Host configuration: {options.host}\n"
        f"  Previous generation: {preflight['generation']}\n"
        f"  Candidate generation: {new_system}\n"
        "  Automatic pruning: disabled",
    )

    old_system = str(preflight["generation"])
    if _remote_unit_exists(options.connection, "mini-pc-actual-backup.service"):
        options.connection.execute("sudo", "systemctl", "start", "mini-pc-actual-backup.service")
    secret_state = None
    if bundle is not None:
        with tempfile.TemporaryDirectory(prefix="mini-pc-secrets-") as name:
            secret_state = stage_remote_secrets(options.connection, bundle, Path(name))
    try:
        options.connection.execute("sudo", f"{new_system}/bin/switch-to-configuration", "switch")
        _health(options.connection, new_system)
    except ProvisioningError as error:
        with suppress(ProvisioningError):
            diagnostics = options.connection.execute(
                "sudo",
                "journalctl",
                "--no-pager",
                "-n",
                "200",
                "-u",
                "mini-pc-application",
                "-u",
                "caddy",
            )
            print(diagnostics, file=os.sys.stderr)
        if secret_state is not None:
            rollback_remote_secrets(options.connection, secret_state)
        options.connection.execute("sudo", f"{old_system}/bin/switch-to-configuration", "switch")
        if secret_state is not None:
            _restart_secret_consumers(options.connection, secret_state.installed_files)
        _health(options.connection, old_system)
        raise ProvisioningError(
            "deployment failed health checks; prior generation and secrets were restored"
        ) from error
    print("Full deployment activated successfully; no generations were pruned", file=os.sys.stderr)
