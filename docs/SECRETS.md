# SSH keys and application secrets

## Threat model

Assume the repository, CI logs, and every Nix store path are readable by people other
than the administrator. Also assume root and a container receiving a credential can
read it. The workflow keeps plaintext secrets out of Git, command arguments, Nix
expressions, derivations, and logs. It does not protect a compromised development
account, server root, or application container.

## Rescue key versus admin key

Both inputs are public SSH keys; their private keys stay on the development PC.

- The rescue key authorizes temporary `root` access and is supplied to
  `scripts/build-iso.sh PUBLIC_KEY_FILE`.
- The admin key authorizes the installed `admin` account and is supplied with
  `--admin-key-file PUBLIC_KEY_FILE` during installation.
- They may be the same for a personal host, but separate keys reduce rotation scope.

`--identity` is the local private key for SSH. Never copy it into this repository.

## Exact application contracts

Create a local mode-0600 dotenv file without putting values in shell history:

```bash
scripts/create-secrets-file.sh \
  --name ACTUAL_PASSWORD \
  --name ACTUAL_BUDGET_ID
```

The parser accepts only these contracts and rejects unknown, duplicate,
empty-required, or partial input before any remote write:

- actual-ai: `ACTUAL_PASSWORD`, `ACTUAL_BUDGET_ID`, and optional
  `ACTUAL_E2E_PASSWORD`;
- Discord bot: `DISCORD_TOKEN`, `DISCORD_BANK_NOTIFICATION_CHANNEL`,
  `ACTUAL_PASSWORD`, `ACTUAL_FILE`, and optional `DISCORD_RECEIPT_CHANNEL`,
  `ACTUAL_ENCRYPTION_PASSWORD`, and `ACTUAL_ACCOUNT`.

Connection URLs, Ollama settings, and dry-run policy are non-secret declarative
values and cannot be overridden by this file. See `application/.env.example`.

Pass the ignored local file during installation:

```bash
nix run .#install -- \
  --target root@nixos-rescue.local \
  --host m710q \
  --identity ~/.ssh/id_ed25519 \
  --admin-key-file ~/.ssh/id_ed25519.pub \
  --application-env-file secrets/compose.env
```

The installer stages it in a mode-0700 temporary directory and splits it into only
the complete service contracts. The target files are
`/var/lib/mini-pc/secrets/actual-ai.env` and/or `discord-bot.env`, owned by root with
mode 0600. A service never receives the other service's credentials. Container
environment values remain visible to root through Docker inspection.

Do not write secrets in Nix `environment` values, Compose YAML, GitHub variables, or
commands. Values referenced from Nix enter the world-readable store.

## Rotation and recovery

Rotate credentials transactionally from the development PC:

```bash
nix run .#deploy -- \
  --target admin@HOST \
  --identity ~/.ssh/id_ed25519 \
  --secrets-only \
  --application-env-file secrets/compose.env
```

The command validates locally, stages root-owned files atomically, restarts only
affected optional units, runs health checks, and restores previous files on failure.
Back up source secrets in an encrypted password manager, not beside the repository.

For multiple hosts or declarative rotation, consider `sops-nix` only after defining
age-key recovery and CI trust. It is intentionally not enabled implicitly.
