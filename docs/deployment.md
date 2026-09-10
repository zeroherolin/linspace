# Deployment details

For a new server, follow [Deploy](../README.md#deploy). This page covers existing installations, bundles and recovery.

## Configuration

`local/site.json` selects the domain, homepage, published key, client settings and Stash authorization. Configure as the account owning the checkout, then deploy with sudo. The wizard expands `~/` paths before saving.

Use `--config local/other.json` on each command for a separate profile. Profiles with different SSH keys should reference distinct key files. Production rejects missing or placeholder filing details; it validates their format, not authority records.

## Existing Caddy

The deployer manages `sites-enabled/linspace.caddy` and its import in `/etc/caddy/Caddyfile`. It preserves other sites and global options. An unmanaged block for the same domain is rejected.

For the supported older single-site linspace layout, inspect the current Caddyfile, then run:

```sh
sudo ./linspace deploy --adopt-existing
```

Complex layouts need a manual merge. A fresh Caddy installation's welcome site is replaced by linspace.

## Upgrade from Stash tokens

Deployment switches writes to SSH signatures and removes the active token file. The backup retains the previous authentication state, and channel data is preserved. Download the current client scripts after upgrading; `--rotate-token` is no longer supported.

## Managed paths

| Path | Purpose |
| --- | --- |
| `/srv/linspace/releases/` | Immutable public releases: directories 0755, files 0644 |
| `/srv/linspace/current` | Active release symlink |
| `/etc/caddy/sites-enabled/linspace.caddy` | Domain and public routes |
| `/etc/caddy/linspace.d/stash.caddy` | Stash routes; root:caddy 0640 |
| `/usr/local/lib/stashd/` | Writer code and root-owned `allowed_signers` |
| `/etc/systemd/system/stashd.{socket,service}` | Socket activation and service isolation |
| `/run/stashd/ssh.sock` | Writer socket; stash:caddy 0660 |
| `/var/lib/stashd/` | Public channel data |
| `/var/lib/linspace/state.json` | Deployment metadata |
| `/var/backups/linspace/` | Configuration, authentication, code, units and release pointer |

Caddy serves only allowlisted paths. The checkout, backups and service code are outside public roots.

## Failure and recovery

Deployment takes a backup before changing managed state. A file or service failure attempts rollback. A final HTTPS check failure retains the installed site for diagnosis; fix the network issue and rerun `./linspace verify`.

To restore a backup printed by deployment:

```sh
sudo ./linspace rollback /var/backups/linspace/BACKUP_NAME
```

Rollback restores managed files and authentication, but keeps current channel contents. It does not change source configuration or remove installed packages/accounts. Restoring a token-based release also restores its token and requires the older clients.

Writes pause during activation and rollback. The SSH and legacy writers use different sockets, and restarts invalidate outstanding signing challenges.

`--dry-run` changes no host services. `--skip-verify` skips only the final HTTPS check; neither proves public availability.

## Deploy a built bundle

On the build machine:

```sh
./linspace build
cd dist
sha256sum linspace-site.tar.gz > linspace-site.tar.gz.sha256
```

On macOS, use `shasum -a 256` in place of `sha256sum`. Transfer the archive and checksum through a trusted channel.

On the server, verify before extracting into a new directory:

```sh
sha256sum --check linspace-site.tar.gz.sha256
mkdir linspace-release
tar --no-same-owner -xzf linspace-site.tar.gz -C linspace-release
cd linspace-release/linspace-site
```

Then follow the included [server bundle README](../packaging/site-README.md). The bundle needs Python 3.9+ and Bash, but no Git checkout or TOML parser. Keep extra files outside the bundle; its checksum manifest rejects additions or edits.

The [Mihomo target bundle](usage/mihomo.md#use-a-target-bundle) is for client proxy installation.

Caddy references: [installation](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) · [imports](https://caddyserver.com/docs/caddyfile/directives/import) · [HTTPS](https://caddyserver.com/docs/automatic-https).
