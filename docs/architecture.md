# Architecture

## Layers

| Location | Responsibility |
| --- | --- |
| `config/` and ignored `local/` | Templates, public presets and operator inputs |
| `scripts/siteconfig.py` | Domain, filing, public-key and client-setting validation |
| `scripts/codex_catalog.py` | Catalog integrity, consistency and refresh |
| `scripts/build.py` | Render files and create checksummed bundles |
| `scripts/deploy.py` | Back up, activate, verify and recover |
| Caddy | HTTPS, route allowlists, caching and body limits |
| `src/mihomo/` | Client proxy tools |
| `src/codex/` | Local API credential setup |
| `src/stash/` | Signed upload clients and the text writer |

Claude JSON is serialized during build; Codex TOML preserves formatting. Catalog checks enforce the [recorded metadata policy](../config/codex/README.md), not the complete product schema. Credentials and operator input paths are excluded from public releases.

## Public routes

| Route | Behavior |
| --- | --- |
| `/` | Site title and filing footer |
| `/ssh/<ssh_public_key_name>` | Selected public key; default name `key.pub` |
| `/mihomo/install`, `/mihomo/sub`, `/mihomo/restart` | Client scripts |
| `/mihomo/assets/geoip-<sha256>.dat` | Pinned GeoIP; immutable caching |
| `/claude/install` | 302 to `https://claude.ai/install.sh` |
| `/claude/config` | Public JSON |
| `/codex/install` | 302 to `https://chatgpt.com/codex/install.sh` |
| `/codex/config`, `/codex/models_1m` | Public TOML and model catalog |
| `/codex/auth` | Script that writes credentials on the client |
| `/stash/upload0`–`7` | Upload scripts |
| `/stash/download0`–`7` | Public GET/HEAD; signed PUT replaces content |
| `/stash/upload`, `/stash/download` | Channel-0 aliases |
| `/stash/keys` | Authorized public keys for client discovery |
| `/stash/challenge` | GET issues a signing challenge; HEAD checks availability |
| `/stash/clear` | GET serves the script; signed POST clears all channels |

Unknown routes return 404. Public text is served with `no-store` and `nosniff`. Installer redirects do not mirror or pin upstream installers.

## State and isolation

Caddy serves immutable files through `/srv/linspace/current` and channel data from `/var/lib/stashd`. The dedicated `stash` account verifies writes through `/run/stashd/ssh.sock`; it has no TCP listener. See the [signature protocol](stash-auth.md).

Uploads replace files atomically. Clearing channels is sequential, not a transaction against concurrent uploads. There is no content history or expiry; connection and verification capacity are bounded.

The Codex auth script backs up and atomically replaces local `auth.json` with mode `600`. It makes no network requests and sends no credentials to the site.

Deployment uses a lock, immutable releases and a switched symlink. Backups cover managed configuration, authorization, code, units and the previous pointer. Channel data is separate. [Paths and recovery](deployment.md).
