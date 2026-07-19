# mini-pc-provision

This package implements the host-side, safety-conscious NixOS provisioning commands.
It is installed by the repository flake and can also be run from a local UV-managed
virtual environment. See the repository `README.md` and `mini-pc-provision --help`.

Pure disk, interface, and report policy is separated from SSH, Nix, dnsmasq, TFTP,
HTTP, Wake-on-LAN, and process adapters. The `provision` command composes those stages
into a private session under `artifacts/sessions/`; lower-level subcommands remain
independently executable and produce stable JSON or path contracts.

The high-level `provision` command creates a dedicated Ed25519 key pair at
`~/.ssh/mini_pc_provision_ed25519` when no key arguments are supplied. Explicit
credentials remain supported by passing the rescue public key, admin public key, and
private identity together.

`deploy` operates on an already installed host. Full mode performs read-only
preflight, builds locally, copies the closure, backs up Actual, stages secrets,
activates the generation, verifies health, and rolls the generation and secrets back
on failure. `--secrets-only` skips the Nix build and restarts only services whose
validated secret file changed. Non-interactive `--yes` is accepted only for the
explicit disposable-CI localhost mode.
