# Operations

Run server commands from the web-server checkout. Keep operator settings and inputs in ignored `local/` files.

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

A new domain needs DNS and filing first. Changing the published SSH filename changes its URL. Each installation has independent settings, authorized keys and channel data.

## Shared client configuration

Select `claude_settings_file` and `codex_config_file` in the site profile, then redeploy. Clients must download the new files and restart their tools. See [client configuration files](usage/client-config.md).

Refresh Codex model metadata with the [catalog procedure](../config/codex/README.md#refresh-and-validate). Client `auth.json` files and their backups must never be published.

## Stash authorized keys

Set `stash_public_key_files` in the site profile:

| Value | Authorization |
| --- | --- |
| `null` or omitted | Reuse `ssh_public_key_file` |
| `["local/laptop.pub", "local/worker.pub"]` | Use these keys independently of SSH publishing |
| `[]` | Disable uploads and clear; reads remain public |

Up to 64 OpenSSH public keys are accepted. Each can upload to any channel and clear all channels. Redeploy after changes; `/stash/keys` lists the active keys without comments or local paths.

To rotate a key, authorize both keys, deploy and test the new key, then remove the old one and deploy again. Changing a reused SSH key also changes Stash authorization; changing only its published filename does not.

Legacy tokens are rejected after upgrading. Rollback backups may retain the old token. [Migration and recovery](deployment.md).

## Diagnostics

```sh
./linspace verify
sudo systemctl status caddy stashd.socket stashd.service
sudo journalctl -u caddy -n 50 --no-pager
sudo journalctl -u stashd.service -n 50 --no-pager
```

To distinguish a source-server problem from a public-network problem:

```sh
./linspace verify --local
```

Loopback verification retains TLS validation but does not prove public access. All verification commands leave channel data unchanged.

If Git reports HTTP/2 framing or ref-listing errors, retry with compatible transport settings:

```sh
git -c http.version=HTTP/1.1 -c protocol.version=1 pull --ff-only
```

HTTPS certificate verification remains enabled. A filing block or public TLS reset must be resolved at the network/hosting layer; a loopback check does not clear it.

## Backups and cleanup

Use [rollback](deployment.md#failure-and-recovery) to restore managed state. Backups and releases are retained until deliberately removed. Keep the active release, releases referenced by retained backups, and Caddy certificate storage.

Channel files are `/var/lib/stashd/download0` through `download7`. A removed channel returns 404; an uploaded empty file returns 200. Use the [Stash client](usage/stash.md#clear) to clear all channels.

## Remove the site

Save needed configuration, channel data and backups. Remove the managed Caddy site and its explicit import, preserving shared wildcard imports and other sites. Validate and reload Caddy, then stop and disable `stashd.socket` and `stashd.service`. Remove only this installation's files and account. The web server has no automatic uninstall command; client uninstall endpoints do not remove the site.
