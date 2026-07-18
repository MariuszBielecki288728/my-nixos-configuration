# Repository layout and generated files

The repository uses names and locations to distinguish source, examples, and local
outputs.

| Path | Kind | Commit? | Purpose |
| --- | --- | --- | --- |
| `flake.nix`, `flake.lock` | configuration | yes | Pinned entry points, packages, checks, and development shell |
| `hosts/`, `modules/`, `rescue/` | configuration | yes | Installed hosts, reusable NixOS modules, and the shared rescue system |
| `python/` | source | yes | UV-managed Python 3.14 provisioning package and tests |
| `scripts/` | source | yes | Minimal shell helpers where process/device handling is natural |
| `application/compose.yaml` | configuration | yes | Digest-pinned application topology; contains no secret values |
| `tests/` | source | yes | Fixtures, NixOS VM tests, and disposable provisioning E2E |
| `artifacts/sessions/` | private runtime | no | Structured evidence from successful and failed provisioning sessions |
| `pxe/*.example`, `keys.example.nix`, `*.env.example` | example | yes | Templates containing visible placeholders, never live credentials |
| `result`, `result-*` | generated | no | Nix result symlinks into `/nix/store` |
| `venv/`, `.direnv/`, `.e2e/`, `artifacts/` | generated/private | no | Python environment, development cache, disposable VM workspace, and discovery reports |
| `pxe/generated/` | generated | no | Copied PXE HTTP/TFTP roots and boot manifest |
| `secrets/`, `.env`, `*.env` | secret/runtime | never | Unencrypted local secret files |

Run `git status --short --ignored` to see ignored files, or inspect one decision with:

```bash
git check-ignore -v result result-pxe secrets/compose.env
```

The committed `.vscode/settings.json` hides the large generated directories from the
Explorer. It does not affect Git and can be overridden in personal VS Code settings.

Do not place a real value in a file merely because its name contains `example`.
Examples are documentation and are committed publicly.
