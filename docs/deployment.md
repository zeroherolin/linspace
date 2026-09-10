# Deployment details

Start with the [complete deployment steps](../README.md#deploy). The selected site JSON supplies the domain, homepage, public key and published filename, Claude JSON, and Codex TOML. The Codex catalog is bundled from `config/codex/models-1m.json`. Source deployment needs Python 3.9+ and `tomli` on Python below 3.11; extracted bundles need no TOML parser.

## Existing Caddy

The deployer manages `/etc/caddy/sites-enabled/linspace.caddy` and imports it from `/etc/caddy/Caddyfile`. It preserves other sites and global options and reuses an existing covering import glob. A fresh Caddy installation's welcome site is replaced by the managed import.

An unmanaged block for the same domain is rejected. After inspecting an older single-site linspace block rooted at `/srv/linspace`, adopt it with:

```sh
sudo ./linspace deploy --adopt-existing
```

Complex or shared layouts need a deliberate manual merge. Existing token hashes are preserved. If an adopted installation has no plaintext token at the current path, keep using the previous token or rotate it explicitly.

## Managed paths

| Path | Purpose |
| --- | --- |
| `/srv/linspace/releases/<id>/` | Public release; directories 0755, files 0644 |
| `/srv/linspace/current` | Active release symlink |
| `/etc/caddy/sites-enabled/linspace.caddy` | Domain and public routes |
| `/etc/caddy/linspace.d/stash.caddy` | Stash routes and bcrypt hash; root:caddy 0640 |
| `/etc/linspace/stash-token` | Plaintext token; root-only 0600, parent 0700 |
| `/usr/local/lib/stashd/stashd.py` | Writer implementation |
| `/etc/systemd/system/stashd.{socket,service}` | Socket activation and isolation |
| `/run/stashd/stashd.sock` | Unix write transport; stash:caddy 0660 |
| `/var/lib/stashd/` | Public channel data |
| `/var/lib/linspace/state.json` | Active deployment metadata |
| `/var/backups/linspace/<timestamp>/` | Managed configuration, token, code, units, release pointer |

The checkout, tokens, backups, and service code are outside the public roots. Caddy serves only allowlisted paths.

## Failure and recovery

Deployment checks inputs and checksums, installs missing dependencies, acquires a lock, snapshots managed state, publishes files, activates services, and verifies HTTPS.

- A managed-file or service failure attempts to restore the snapshot; failed recovery retains the backup for repair.
- Newly installed packages/accounts are not removed by rollback.
- A final HTTPS verification failure leaves the installation in place. Fix DNS, firewall, or certificates, then rerun `./linspace verify`.
- `--dry-run` builds and checks the manifest without changing host services. It does not prove Caddy syntax, certificate issuance, or public reachability.
- `--skip-verify` skips only the final network check; a separate successful verification is still needed.

Use a backup path printed by deployment:

```sh
sudo ./linspace rollback /var/backups/linspace/BACKUP_NAME
```

Rollback restores the previous managed files, token and release, but keeps current channel contents. It does not edit `local/site.json` or selected input files; reconcile those before the next deploy.

## Deploy a built bundle

On the build machine:

```sh
./linspace build
awk '$2 == "linspace-site.tar.gz" { print }' dist/SHA256SUMS > dist/linspace-site.tar.gz.sha256
```

Transfer the archive and checksum through a trusted channel. On the web server, from their directory:

```sh
sha256sum --check linspace-site.tar.gz.sha256
release_dir=$(mktemp -d ./linspace-release.XXXXXX)
tar --no-same-owner -xzf linspace-site.tar.gz -C "$release_dir"
cd "$release_dir/linspace-site"
sha256sum --check SHA256SUMS
bash linspace --dry-run
sudo bash linspace
python3 verify.py
```

The bundle includes rendered public files and deployment tools; no Git or build step is needed there. Rebuild to change content or domains. Extra files invalidate its manifest, so keep logs and editor backups outside it. The separate Mihomo bundle is covered in the [target guide](usage/mihomo.md#use-a-target-bundle).

Caddy references: [installation](https://caddyserver.com/docs/install#debian-ubuntu-raspbian), [imports](https://caddyserver.com/docs/caddyfile/directives/import), [automatic HTTPS](https://caddyserver.com/docs/automatic-https), [validation](https://caddyserver.com/docs/command-line#caddy-validate).
