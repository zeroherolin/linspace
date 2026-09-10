# linspace server bundle

This bundle contains the domain/homepage, SSH key when selected, Mihomo scripts/data, Claude JSON, Codex TOML/model catalog, Stash clients/services, and deployment tools. Claude and Codex installer routes redirect upstream. Site values, including the public SSH key filename, are in `release.json`.

Use a Debian 12+ or Ubuntu 22.04+ systemd host with root access, Python 3.9+ and Bash. Existing Caddy must be 2.10+; missing runtime tools/Caddy are installed from apt. This rendered bundle needs no Git checkout, build step or TOML parser. DNS and filing must be complete and TCP 80/443 reachable.

Verify the archive against a trusted checksum before extracting. From the extracted `linspace-site` directory:

```sh
sha256sum --check SHA256SUMS
bash linspace --dry-run
sudo bash linspace
python3 verify.py
```

Omit sudo as root. Deployment backs up managed state, publishes an immutable release, switches `/srv/linspace/current`, activates Caddy/Stash, and checks HTTPS. Existing tokens and channel data are preserved. New tokens are stored at `/etc/linspace/stash-token`, mode 0600, and never included here.

```sh
python3 verify.py --local
sudo bash linspace --rotate-token
sudo bash linspace --rollback /var/backups/linspace/BACKUP_NAME
```

Loopback verification retains certificate validation but does not prove public access. Managed installation failure attempts restoration; a final HTTPS failure retains the installed state for diagnosis. Rollback restores the old token/code/release but not channel contents or source configuration. Added packages/accounts remain installed.

Reconfigure and rebuild in the source repository to change domains or public files. Keep logs and extra files outside this extracted directory: the manifest rejects unlisted or changed files. Backups remain under `/var/backups/linspace/` for deliberate cleanup.

A release marked as a test build requires `--internal-test`. Add `--local` for loopback verification; TLS validation remains enabled.
