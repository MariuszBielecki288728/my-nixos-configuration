# Command reference

Every operator-facing command supports `--help`. Provisioning commands are implemented
by the typed Python 3.14 package in `python/`; prefer the flake applications because
they supply pinned Python and external runtime tools.

| Command | Destructive? | Description |
| --- | --- | --- |
| `nix run .#discover -- …` | no | Collect remote DMI, storage, network, PCI, and USB JSON |
| `nix run .#select-disk -- …` | no | Apply the fail-closed disk policy to a discovery report |
| `nix run .#install -- …` | yes, after confirmation | Discover, select, install, reboot, and verify |
| `mini-pc-provision verify-installed` | no | Poll SSH, systemd units, and application HTTP health |
| `scripts/build-iso.sh` | no | Inject a rescue public key through a temporary wrapper flake |
| `scripts/create-secrets-file.sh` | local secret write | Interactively create a mode-0600 Compose dotenv file |
| `scripts/inspect-iso.sh` | no | Print file type, SHA-256, and size |
| `scripts/run-rescue-vm.sh` | disposable VM only | Boot rescue with a temporary qcow2 disk |
| `scripts/write-usb.sh` | yes | Write an ISO only to a confirmed removable whole device |
| `pxe/build-pxe.sh` | generated files only | Copy the built PXE bundle into the ignored HTTP root |
| `scripts/check.sh` | no | Run format, shell, selector, and flake checks |

For Python development, create `./venv`, install UV into it, and run
`uv sync --project python --active`. Ruff, Black, pytest, coverage, and pre-commit are
declared in `python/pyproject.toml` and pinned in `python/uv.lock`.

Internal files under `tests/e2e/` are CI building blocks. Run the supported entry point
as `nix develop -c timeout 100m tests/e2e/run.sh`; it creates only `.e2e/target.raw`.

Use `COMMAND --help` for options, defaults, examples, exit behavior, and safety notes.
