# Operations

## Update or change settings

Keep `local/site.json`, your copied public key, and any custom public Claude settings in the ignored `local/` directory. From the repository root, inspect `git status --short`, resolve source edits or conflicting untracked files, update code with `git pull --ff-only`, then run `sudo ./linspace deploy`. When using a non-default profile, pass the same `--config` path to every configuration-dependent command. Deployment always rebuilds for the current configuration, preserves channel data, and keeps the token unless `--rotate-token` is explicitly provided.

Edit site values with `./linspace configure`. A new domain must already be resolved to this host and filed before it replaces the configured domain. All generated URLs, including downloaded client scripts, follow the new configuration. Existing clients with old URLs must switch to the new hostname.

## Stash token

On a new deployment, read `/etc/linspace/stash-token` as root and store its value in a password manager. Caddy's fragment contains only the bcrypt hash. Never put the token into the public release, repository, or a stash channel.

```sh
sudo ./linspace deploy --rotate-token
sudo cat /etc/linspace/stash-token
```

An adopted installation keeps its previous hash. If its plaintext token is not present at the new standard path, use the previous password-manager copy or rotate explicitly. Suspected exposure calls for rotation and deliberate review of the public channel contents.

## Diagnostics

```sh
./linspace verify
./linspace verify --local
sudo systemctl status caddy stashd.socket stashd.service
sudo journalctl -u caddy -n 100 --no-pager
sudo journalctl -u stashd.service -u stashd.socket -n 100 --no-pager
sudo curl -sS --unix-socket /run/stashd/stashd.sock -o /dev/null -w '%{http_code}\n' http://stashd/
```

The direct writer GET check returns 405. Passive verification never modifies channels: authentication is checked with PUT to the clear path, which the writer cannot execute as a clear operation.

## Backups and cleanup

[Deployment](deployment.md) lists managed locations and rollback semantics. Backups and public releases are retained automatically; no scheduled pruning is installed. Before removing an old release, check `/srv/linspace/current` and the `current` entries in retained backup `snapshot.json` files. Keep any release needed for a future rollback. Keep Caddy certificate storage persistent; it is managed separately by Caddy.

Channel files are `/var/lib/stashd/download0` through `download7`. An administrator can remove a particular channel file to make its URL return 404; no service restart is needed. Uploading an empty file instead leaves a populated, zero-byte resource. The authenticated client clear command removes all eight channels; it is not part of deployment verification.

## Remove the managed site

For a deliberate uninstall, first save any required tokens, channel data, and backups. Check how the main Caddyfile includes the site:

- If it contains the explicit `import /etc/caddy/sites-enabled/linspace.caddy` line, remove only that line and the managed site file.
- If a shared wildcard import includes the managed file, remove only `/etc/caddy/sites-enabled/linspace.caddy`. Keep the wildcard import so other sites remain configured.

Validate the resulting Caddy configuration and reload it before removing public files. Then disable/stop `stashd.socket` and `stashd.service` and remove only this installation's files and account as appropriate. Preserve unrelated sites and certificate storage. The tool has no automatic destructive uninstall command.
