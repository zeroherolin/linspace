# Architecture

`local/site.json` is the default deployment configuration. An alternative JSON profile can be selected with `--config`; each build uses exactly one profile. `scripts/siteconfig.py` validates it as JSON data; no configuration is evaluated by a shell. Hostnames are normalized and constrained to DNS names, required homepage fields are checked, and display text is HTML-escaped. Optional SSH input is validated as a public key. Public Claude settings default to an empty object.

The builder expands modular shell/Python source includes and template tokens into self-contained public scripts. It validates both compressed and raw GeoIP hashes, renders the homepage and Caddy configuration, and packages a checksummed server release and a separate mihomo target bundle. Release metadata contains public site values rather than the input-file paths from the local profile. Releases include the selected public settings content; they do not include a stash token.

```text
Your domain + local/site.json
          |
          v
       builder ---> checksummed release bundle
                          |
                          v
                      deployer
                          |
HTTPS ---> Caddy ---------+-- /srv/linspace/current (public files)
              |
              +-- public GET/HEAD ---> /var/lib/stashd/download[0-7]
              |
              +-- authenticated PUT/POST ---> Unix socket ---> stashd
              |
              +-- Claude installer redirect ---> claude.ai
```

Caddy uses a managed site import so unrelated sites remain in the main Caddyfile. It handles TLS, redirects, no-sniff headers, per-route caching, write authentication, and the 1 MiB body limit. Static files and stash reads have explicit route allowlists; other paths return 404.

| Route | Behavior |
| --- | --- |
| `/` | Configured homepage and filing footer |
| `/ssh/key.pub` | Public key, only when configured; `/ssh/linz.pub` remains a compatibility alias |
| `/mihomo/install`, `/mihomo/sub`, `/mihomo/restart` | Self-contained target scripts |
| `/mihomo/assets/geoip-<sha256>.dat` | Pinned data with immutable caching |
| `/claude/install` | 302 to the official installer |
| `/claude/config` | Public settings JSON as plain text |
| `/stash/upload0` … `/stash/upload7` | Upload scripts for the configured domain |
| `/stash/download0` … `/stash/download7` | Public GET/HEAD; authenticated PUT replaces a channel |
| `/stash/upload`, `/stash/download` | Channel-0 aliases |
| `/stash/clear` | GET serves the clear script; authenticated POST clears all channels |

Stashd runs as `stash` under systemd socket activation, with no TCP listener. Its unit restricts the process to Unix sockets and its state directory. Channel writes use a temporary file, fsync, and rename; readers see a complete old or new file. Clear unlinks the eight files sequentially, so it is not a transaction against concurrent uploads. There is no rate limiting, history, or automatic expiry.

The deployment lock serializes managed-file changes and rollback. Builds and dependency installation happen before that lock is acquired. Public content switches through a symlink; configuration/token/code snapshots support recovery. Detailed boundaries and paths are in [deployment](deployment.md).
