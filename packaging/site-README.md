# linspace server bundle

This bundle contains the configured website, SSH key when selected, client installers and shared settings, Stash and deployment tools. Large application/data downloads are external. Site values are in `release.json`.

Use Debian 12+ or Ubuntu 22.04+ with systemd, root/sudo, Python 3.9+ and Bash. DNS and filing must be complete, with TCP 80/443 reachable. Install curl, CA certificates and OpenSSH first. Existing Caddy must be 2.10+; missing Caddy is installed with a verified download fallback. No Git checkout or TOML parser is needed.

## Deploy

Verify the archive against a trusted checksum before extraction. From the extracted `linspace-site` directory:

```sh
sha256sum --check SHA256SUMS
bash linspace --dry-run
sudo bash linspace
python3 verify.py
```

Omit sudo as root. Deployment backs up managed state and preserves channel data. Stash writes use the authorized SSH keys in the bundle. Upgrading removes the active legacy token after taking a rollback backup.

## Diagnose and restore

```sh
python3 verify.py --local
sudo bash linspace --rollback /var/backups/linspace/BACKUP_NAME
```

Loopback verification retains TLS checks but does not prove public access. Managed installation failures attempt restoration; final HTTPS failures retain the installed state for diagnosis.

Rollback restores authentication, code and the release, not channel contents or source configuration. Installed packages/accounts remain. Backups are retained for deliberate cleanup.

Rebuild in the source repository to change site settings or public files. Keep logs and extra files outside this bundle; its manifest rejects additions or edits.

Test builds require `--internal-test`. Add `--local` for loopback verification.
