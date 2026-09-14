# Operations

Run server commands from the checkout as the account that owns it; deploy with `sudo`. Keep operator settings and inputs in ignored `local/` files. For a first deployment, follow the [README](../README.md#deploy).

## Update and reconfigure

```sh
git status --short
git pull --ff-only
sudo ./linspace deploy
```

Resolve source edits before pulling. To change site settings:

```sh
./linspace configure
sudo ./linspace deploy
```

A new domain needs DNS and filing first. Changing the published SSH filename changes its URL. Use `--config local/other.json` on every command for a separate profile; profiles with different SSH keys should reference distinct key files.

The public `/help` page is built from `docs/help.md`: edit it, run `./linspace check`, then deploy.

If Git reports HTTP/2 framing errors, retry with `git -c http.version=HTTP/1.1 -c protocol.version=1 pull --ff-only`.

## Shared client configuration

Select `claude_settings_file` and `codex_config_file` in the site profile, then redeploy. Clients download the new files themselves and restart their tools. Client `auth.json` files and tokens must never be published. Refresh Codex model metadata with the [catalog procedure](architecture.md#codex-preset-and-catalog).

## Stash authorized keys

Set `stash_public_key_files` in the site profile:

| Value | Authorization |
| --- | --- |
| `null` or omitted | Reuse `ssh_public_key_file` |
| `["local/laptop.pub", "local/worker.pub"]` | Use these keys independently of SSH publishing |
| `[]` | Disable uploads and clear; reads remain public |

Up to 64 OpenSSH public keys are accepted; each can upload to any channel and clear all channels. Redeploy after changes. `/stash/keys` lists the active keys without comments or local paths.

To rotate a key, authorize both keys, deploy and test the new key, then remove the old one and deploy again. Changing a reused SSH key also changes Stash authorization; changing only its published filename does not. Legacy tokens are rejected after upgrading; rollback backups may retain the old token.

## Existing Caddy

The deployer manages `sites-enabled/linspace.caddy` and its import in `/etc/caddy/Caddyfile`, preserving other sites and global options. An unmanaged block for the same domain is rejected. For the older single-site linspace layout, inspect the current Caddyfile and run:

```sh
sudo ./linspace deploy --adopt-existing
```

Complex layouts need a manual merge. A fresh Caddy installation's welcome site is replaced.

## Diagnostics

```sh
./linspace verify
sudo systemctl status caddy stashd.socket stashd.service
sudo journalctl -u caddy -n 50 --no-pager
sudo journalctl -u stashd.service -n 50 --no-pager
```

`./linspace verify --local` checks loopback with normal TLS validation to separate a server problem from a network problem; it does not prove public access. Verification never changes channel data. Filing blocks and public TLS resets must be resolved at the network or hosting layer.

## Failure and recovery

Deployment snapshots managed files before changing them. A file or service failure restores the snapshot automatically. A final HTTPS check failure keeps the installed site for diagnosis; fix the network issue and rerun `./linspace verify`. Deployment and rollback share a lock; a competing run exits before changing host state.

To restore a backup printed by deployment:

```sh
sudo ./linspace rollback /var/backups/linspace/BACKUP_NAME
```

Rollback restores managed files, authentication and the release pointer, but keeps current channel contents and does not remove installed packages or accounts. Restoring a token-based release restores its token and requires the older clients.

`--dry-run` changes nothing on the host. `--skip-verify` skips only the final HTTPS check.

## Backups and cleanup

Backups under `/var/backups/linspace/` and releases under `/srv/linspace/releases/` are retained until deliberately removed. Keep the active release, releases referenced by retained backups, and Caddy certificate storage.

Channel files are `/var/lib/stashd/download0` through `download7`. A removed file returns 404; an uploaded empty file returns 200.

## Remove the site

Save needed configuration, channel data and backups. Remove `/etc/caddy/sites-enabled/linspace.caddy` and its import line, preserving other sites; validate and reload Caddy. Stop and disable `stashd.socket` and `stashd.service`, then remove `/usr/local/lib/stashd`, `/srv/linspace`, `/var/lib/linspace`, `/var/lib/stashd` and the `stash` account. There is no automatic server uninstall; client uninstall endpoints do not touch the server.

## Deploy from a bundle

Where the server has no Git access, build on another machine and transfer the archive with its checksum through a trusted channel:

```sh
./linspace build
cd dist && sha256sum linspace-site.tar.gz > linspace-site.tar.gz.sha256
```

On macOS use `shasum -a 256`. The server needs only Python 3.9+ and Bash; extract and follow the [bundle README](site-bundle.md). The [Mihomo bundle](mihomo-bundle.md) serves clients without site access. Test bundles require `--internal-test`.
