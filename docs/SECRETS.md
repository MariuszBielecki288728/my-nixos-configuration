# SSH keys and application secrets

## Threat model

Assume the Git repository, GitHub Actions logs, and every Nix store path are readable
by people other than the machine administrator. Also assume root on the installed host
can read application secrets. The workflow therefore keeps plaintext secrets out of
Git, command-line arguments, generated Nix expressions, and derivations.

This protects against accidental Git/Nix-store disclosure. It does not protect a
compromised development account, root on the server, or a compromised application
container that legitimately receives a secret.

## Rescue key versus admin key

Both inputs are **public** SSH keys; the corresponding private key stays on the
development PC.

- The rescue key authorizes `root` in the temporary rescue ISO. Supply it while
  building the ISO with `scripts/build-iso.sh PUBLIC_KEY_FILE`.
- The admin key authorizes the normal `admin` account after installation. Supply it
  to `mini-pc-provision install` (or `nix run .#install`) with
  `--admin-key-file PUBLIC_KEY_FILE`.
- They may be the same public key for a small personal installation. Separate keys
  are preferable when rescue access and routine administration have different trust
  or rotation requirements.

The `--identity` argument is the local **private** key used to make those SSH
connections. Never copy it into this repository.

## Docker Compose environment secrets

Create a local root-only dotenv file interactively; values are read without terminal
echo and are not placed in shell history:

```bash
scripts/create-secrets-file.sh \
  --name DATABASE_PASSWORD \
  --name API_TOKEN
```

The default output is `secrets/compose.env`, which is ignored by Git and mode 0600.
Pass it during the destructive installation:

```bash
nix run .#install -- \
  --target root@nixos-rescue.local \
  --host m710q \
  --identity ~/.ssh/id_ed25519 \
  --admin-key-file ~/.ssh/id_ed25519.pub \
  --application-env-file secrets/compose.env
```

The installer stages the file in a mode-0700 temporary directory and gives it to
`nixos-anywhere --extra-files`. It arrives as
`/var/lib/mini-pc/secrets/compose.env`, owned by root with mode 0600. Compose loads it
through `env_file`; services use only variables they explicitly reference.

Do not use `environment = { SECRET = "..."; };` in a Nix module: that writes the value
to the world-readable Nix store. Do not put secrets directly in `compose.yaml`, GitHub
repository variables, command arguments, or CI logs.

## Rotation and recovery

The current helper is installation-oriented. Rotate a Compose secret by securely
replacing `/var/lib/mini-pc/secrets/compose.env` on the host and restarting
`mini-pc-application.service`. Back up the source secret file in an encrypted password
manager, not beside the repository.

For multiple hosts or declarative secret rotation, adopt `sops-nix` with an age key
stored outside the repository. That requires a separate key-recovery and CI trust
design; it is intentionally not enabled implicitly here.
