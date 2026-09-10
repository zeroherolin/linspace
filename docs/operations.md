# Operations

Run commands from the web-server checkout. Keep `local/site.json`, the public key and custom client configuration files in ignored `local/` storage.

## Update and reconfigure

```sh
git status --short
git pull --ff-only
sudo ./linspace deploy
```

Resolve source changes before pulling. Python 3.9/3.10 requires `python3-tomli`. Change settings with `./linspace configure`, then redeploy. Use the same `--config` path for a named profile. Re-save profiles containing literal `~/` input paths as the intended account before deploying with sudo.

A new domain needs DNS and filing first. Changing `ssh_public_key_name` publishes the key at the new filename and removes the old URL. Clients must update their URLs and explicitly reapply shared configuration. Installations do not synchronize tokens, content or settings.

## Shared client configuration

Select the intended `claude_settings_file` and `codex_config_file` in the site profile. To use bundled presets, select `config/claude/settings.json` and `config/codex/config.toml`. If published settings differ from the expected content, compare the selected input and active release.

Refresh Codex model metadata through the [catalog procedure](../config/codex/README.md#refresh-and-validate). Clients save `/codex/models_1m` beside `config.toml` as `models-1m.json`, then restart Codex. Configuration downloads respect `CLAUDE_CONFIG_DIR` and `CODEX_HOME`.

## Token

Read the token and store it in a password manager:

```sh
sudo cat /etc/linspace/stash-token
```

To issue a replacement:

```sh
sudo ./linspace deploy --rotate-token
sudo cat /etc/linspace/stash-token
```

All writers and clear clients need the replacement token. An adopted installation may have only a bcrypt hash; use its existing token or rotate to create the standard token file.

## Diagnostics

```sh
./linspace verify
./linspace verify --local
sudo systemctl status caddy stashd.socket stashd.service
sudo journalctl -u caddy -n 80 --no-pager
sudo journalctl -u stashd.service -u stashd.socket -n 80 --no-pager
```

Verification leaves Stash data unchanged. `--local` checks loopback using the configured hostname and TLS certificate; it does not establish public access. The direct writer check should return 405:

```sh
sudo curl -sS --unix-socket /run/stashd/stashd.sock -o /dev/null -w '%{http_code}\n' http://stashd/
```

## Backups and cleanup

Use [deployment recovery](deployment.md#failure-and-recovery) for rollback. Releases and backups are retained without automatic pruning. Keep the active release and every release referenced by a retained backup's `snapshot.json`. Preserve Caddy certificate storage.

Stash files are `/var/lib/stashd/download0` through `download7`. Removing a file makes that channel return 404 without restarting services. Uploading an empty file instead returns 200 with an empty body. The public clear client removes all eight channels.

## Remove the site

Save required tokens, channel data and backups. Remove the managed site file and its explicit import, or only the file when a shared wildcard import covers it. Validate and reload Caddy, then stop/disable `stashd.socket` and `stashd.service`. Remove only this installation's files/account, preserving unrelated sites and certificate storage. There is no automatic uninstall command.
