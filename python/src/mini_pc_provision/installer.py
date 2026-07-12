"""Confirmed remote installation orchestration using pinned Nix tooling."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .discovery import discover
from .disks import select_disk
from .errors import ProvisioningError
from .process import run
from .remote import SshConnection

PUBLIC_KEY_PATTERN = re.compile(r"^ssh-(?:ed25519|rsa|ecdsa-[^ ]+) [A-Za-z0-9+/=]+")
ENV_LINE_PATTERN = re.compile(r"^(?:#.*|\s*|[A-Za-z_][A-Za-z0-9_]*=.*)$")
HOST_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")


def project_root() -> Path:
    """Find the immutable packaged source or the current repository root."""
    configured = os.environ.get("PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "flake.nix").is_file():
            return candidate
    raise ProvisioningError(
        "cannot locate project flake; run from the repository or set PROJECT_ROOT"
    )


def read_public_key(path: Path) -> str:
    """Read and validate the first OpenSSH public-key line."""
    try:
        key = path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError) as error:
        raise ProvisioningError(f"public key file is not readable: {path}") from error
    if not PUBLIC_KEY_PATTERN.match(key):
        raise ProvisioningError("admin key file does not contain an OpenSSH public key")
    return key


def validate_environment_file(path: Path) -> None:
    """Require a private regular dotenv file with syntactically safe lines."""
    try:
        details = path.stat()
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ProvisioningError(f"application environment file is not readable: {path}") from error
    if not stat.S_ISREG(details.st_mode):
        raise ProvisioningError(f"application environment file is not a regular file: {path}")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise ProvisioningError("application environment file must have mode 0600 or stricter")
    if any(not ENV_LINE_PATTERN.fullmatch(line) for line in lines):
        raise ProvisioningError(
            "application environment file must contain only NAME=value lines, comments, or blanks"
        )


@dataclass(frozen=True, slots=True)
class InstallOptions:
    """Validated operator inputs for one destructive installation."""

    connection: SshConnection
    host: str
    admin_key_file: Path
    requested_disk: str | None = None
    application_env_file: Path | None = None
    assume_yes: bool = False
    ci_disposable: bool = False


def install(options: InstallOptions) -> None:
    """Discover, confirm, install, reboot, and verify one target host."""
    if not options.connection.target.startswith("root@"):
        raise ProvisioningError("rescue target must explicitly use root@HOST")
    if not HOST_PATTERN.fullmatch(options.host):
        raise ProvisioningError("invalid host configuration name")
    if options.assume_yes and not options.ci_disposable:
        raise ProvisioningError("--yes is accepted only together with --ci-disposable")
    admin_key = read_public_key(options.admin_key_file)
    if options.application_env_file:
        validate_environment_file(options.application_env_file)
    root = project_root()
    if not (root / "flake.nix").is_file():
        raise ProvisioningError(f"project flake is unavailable: {root}")
    options.connection.execute("true")

    with tempfile.TemporaryDirectory(prefix="mini-pc-install-") as temporary_name:
        temporary = Path(temporary_name)
        report_path, report = discover(options.connection, temporary / "discovery.json")
        candidate = select_disk(report, options.requested_disk)
        disk = candidate.stable_path
        print("DESTRUCTIVE INSTALLATION SUMMARY", file=os.sys.stderr)
        print(f"  Rescue target: {options.connection.target}", file=os.sys.stderr)
        print(f"  NixOS configuration: {options.host}", file=os.sys.stderr)
        print(f"  Whole disk to erase: {disk}", file=os.sys.stderr)
        print(
            f"  Device: {candidate.disk.model or 'unknown'} | {candidate.disk.size} bytes | "
            f"serial {candidate.disk.serial or 'unknown'}",
            file=os.sys.stderr,
        )
        print(f"  Discovery report: {report_path} (temporary)", file=os.sys.stderr)
        if not options.assume_yes:
            confirmation = input("Type the full disk path to continue: ")
            if confirmation != disk:
                raise ProvisioningError("confirmation did not exactly match the selected disk")
        else:
            print("CI disposable-disk confirmation bypass is active", file=os.sys.stderr)

        (temporary / "flake.nix").write_text(
            "{\n"
            f"  inputs.base.url = {json.dumps(f'path:{root}')};\n"
            "  outputs = { base, ... }: {\n"
            f'    nixosConfigurations."{options.host}" = '
            f'base.nixosConfigurations."{options.host}".extendModules {{\n'
            "      modules = [ ./runtime.nix ];\n"
            "    };\n"
            "  };\n"
            "}\n",
            encoding="utf-8",
        )
        (temporary / "runtime.nix").write_text(
            "{\n"
            f"  my.install.targetDisk = {json.dumps(disk)};\n"
            f"  my.ssh.authorizedKeys = [ {json.dumps(admin_key)} ];\n"
            "}\n",
            encoding="utf-8",
        )
        anywhere = [
            "nix",
            "run",
            f"path:{root}#nixos-anywhere",
            "--",
            "--flake",
            f"{temporary}#{options.host}",
            "--target-host",
            options.connection.target,
            "--ssh-port",
            str(options.connection.port),
            "--copy-host-keys",
        ]
        if options.connection.identity:
            anywhere.extend(["-i", str(options.connection.identity)])
        known_hosts = os.environ.get("SSH_USER_KNOWN_HOSTS_FILE")
        if known_hosts:
            anywhere.extend(["--ssh-option", f"UserKnownHostsFile={known_hosts}"])
        if options.application_env_file:
            secret_dir = temporary / "extra-files/var/lib/mini-pc/secrets"
            secret_dir.mkdir(parents=True, mode=0o700)
            destination = secret_dir / "compose.env"
            shutil.copyfile(options.application_env_file, destination)
            destination.chmod(0o600)
            anywhere.extend(
                [
                    "--extra-files",
                    str(temporary / "extra-files"),
                    "--chown",
                    "/var/lib/mini-pc/secrets",
                    "0:0",
                ]
            )
        print(
            "Starting pinned nixos-anywhere; this is the first destructive operation",
            file=os.sys.stderr,
        )
        run(anywhere)

    installed = SshConnection(
        target=f"admin@{options.connection.target.partition('@')[2]}",
        port=options.connection.port,
        identity=options.connection.identity,
    )
    verify_installed(installed, timeout=600)


def verify_installed(connection: SshConnection, timeout: int = 300) -> None:
    """Wait for SSH, systemd services, and application HTTP health."""
    print(
        f"Waiting up to {timeout}s for installed-system SSH at "
        f"{connection.target}:{connection.port}",
        file=os.sys.stderr,
    )
    if not connection.wait_until_ready(timeout):
        raise ProvisioningError("installed-system SSH did not become ready")
    deadline = time.monotonic() + timeout
    health = (
        "systemctl is-active --quiet sshd docker mini-pc-application && "
        "curl --fail --silent --max-time 10 http://127.0.0.1:8080/ >/dev/null"
    )
    while time.monotonic() < deadline:
        try:
            connection.execute("sh", "-c", health)
            print(
                "Installed system, Docker Compose service, and HTTP health are ready",
                file=os.sys.stderr,
            )
            return
        except ProvisioningError:
            time.sleep(5)
    diagnostics = (
        "systemctl --no-pager --full status sshd docker mini-pc-application; "
        "curl --fail --show-error --max-time 10 http://127.0.0.1:8080/"
    )
    with suppress(ProvisioningError):
        connection.execute("sh", "-c", diagnostics)
    raise ProvisioningError(f"installed services did not become healthy within {timeout}s")
