"""Small, observable subprocess boundary used by provisioning commands."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from .errors import ProvisioningError


def run(
    arguments: Sequence[str | os.PathLike[str]],
    *,
    capture_output: bool = False,
    check: bool = True,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    input_text: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an argument-vector command and translate common OS failures."""
    command = [os.fspath(item) for item in arguments]
    try:
        return subprocess.run(  # noqa: S603 - every caller supplies an argument vector.
            command,
            capture_output=capture_output,
            check=check,
            cwd=cwd,
            env=env,
            input=input_text,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ProvisioningError(f"required command is unavailable: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise ProvisioningError(f"command timed out after {timeout}s: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip()
        suffix = f": {detail}" if detail else ""
        raise ProvisioningError(
            f"command failed ({error.returncode}): {command[0]}{suffix}"
        ) from error
