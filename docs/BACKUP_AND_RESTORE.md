# Actual backup and restore

`mini-pc-actual-backup.timer` creates a daily consistent archive under
`/var/lib/mini-pc/backups/actual`. The helper takes a lock, stops Actual, creates and
lists a gzip archive, atomically renames it, restarts Actual, and removes archives
older than the configured retention. A failed archive is removed and Actual is
restarted by the cleanup trap.

Run and inspect a backup:

```bash
sudo systemctl start mini-pc-actual-backup.service
sudo journalctl -u mini-pc-actual-backup.service
sudo tar -tzf /var/lib/mini-pc/backups/actual/actual-REVIEWED_TIMESTAMP.tar.gz
```

Before restore, copy the selected archive off the host and verify it. Restore is
deliberately interactive and requires the exact absolute archive path:

```bash
sudo mini-pc-actual-restore \
  /var/lib/mini-pc/backups/actual/actual-REVIEWED_TIMESTAMP.tar.gz
```

The helper validates before stopping Actual, extracts into staging, keeps the prior
data as a local rollback, and restores that rollback if the new container does not
become healthy. After success, run `sudo mini-pc-application-health` and open the
budget from a trusted client.

Local retention is not disaster recovery. Copy verified archives to encrypted,
off-machine storage and test restore periodically. Encryption keys must stay outside
Git and the Nix store; automated encrypted backups require a separate key-recovery
and threat-model decision.
