# Actual Budget application stack

`modules/application.nix` declares Actual Budget behind native Caddy HTTPS. Actual is
published only on `127.0.0.1:5006`; Caddy is the sole LAN entry point and nftables
allows TCP 443 only from reviewed `my.actualStack.trustedLanCidrs`. Actual and the
Discord bot share an internal Compose network. The bot also uses a dedicated egress
bridge to reach Discord without publishing an inbound port. A separate private proxy
bridge is required for Docker's loopback publication.

Images are fetched at reviewed registry manifest digests into fixed-output Nix
archives, copied with the system closure, loaded locally, and used with
`pull_policy: never`. Deterministic `pinned-<digest-prefix>` local tags are necessary
because Docker archive loading does not preserve registry `RepoDigests`; the complete
source and linux/amd64 content digests remain asserted in the Nix image inventory.

Actual is the only default service. The optional Discord profile is independently
gated, and its image is pinned to the reviewed v0.5.0 OCI revision.

Persistent data is under `/var/lib/mini-pc`; root-only secrets and backups are kept in
separate mode-0700 directories. See [application operations](../docs/APPLICATION_OPERATIONS.md),
[secrets](../docs/SECRETS.md), and [backup/restore](../docs/BACKUP_AND_RESTORE.md).
