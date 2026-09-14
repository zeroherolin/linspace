# linspace server bundle

A built linspace release: the configured website, published SSH key when selected, client scripts, shared settings, Stash service and deployment tools. Site values are in `release.json`. Application downloads stay external.

Use Debian 12+ or Ubuntu 22.04+ with systemd, root/sudo, Python 3.9+, Bash, curl, CA certificates and OpenSSH. DNS and filing must be complete, with TCP 80/443 reachable. Missing Caddy is installed with a verified download fallback; existing Caddy must be 2.10+.

## Deploy

Verify the archive against a trusted checksum, extract it into a new directory, then from `linspace-site`:

```sh
sha256sum --check SHA256SUMS
bash linspace --dry-run
sudo bash linspace
python3 verify.py
```

Omit `sudo` as root. Deployment backs up managed state and preserves channel data. Stash writes use the authorized SSH keys in the bundle; upgrading removes any legacy token after taking a rollback backup. The client uninstall routes are for client machines and do not remove the server site.

## Diagnose and restore

```sh
python3 verify.py --local
sudo bash linspace --rollback /var/backups/linspace/BACKUP_NAME
```

Loopback verification keeps TLS checks but does not prove public access. Failures during activation restore the previous state automatically; a final HTTPS failure keeps the installed state for diagnosis. Rollback restores authentication, code and the release, not channel contents. Backups are retained until deliberately removed.

Rebuild in the source repository to change site settings or public files. Keep other files outside this directory; the manifest rejects additions or edits. Test builds require `--internal-test`; add `--local` for loopback verification.
