# Application stack

The initial stack is nginx exposed on TCP port 8080. Its image is pinned by digest in
`compose.yaml`. The Nix module fetches the registry manifest-list digest into a
fixed-output linux/amd64 archive while building on the development PC, copies that
archive in the installation closure, and loads it before Compose with
`pull_policy: never`. The installed target therefore needs no registry or Internet
access. Persistent application data belongs under `/var/lib/mini-pc`; back up that
directory before upgrades. Do not put secrets in this directory through Nix, because
values referenced by Nix expressions can be copied to the world-readable Nix store.

Optional environment values are loaded from
`/var/lib/mini-pc/secrets/compose.env`. The installer places that file outside the
Nix store when given `--application-env-file`; see [the secrets guide](../docs/SECRETS.md).
Services should reference only the variables they need.

Container environment variables remain visible to root through Docker inspection.
Prefer file-based credentials for future images that support them.
