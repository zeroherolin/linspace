# Architecture

## Layers

| Layer | Responsibility |
| --- | --- |
| `config/` + ignored `local/` | Schema, templates, defaults, operator inputs |
| `scripts/siteconfig.py` | Validate domain/filing text, SSH key, Claude JSON and Codex TOML |
| `scripts/codex_catalog.py` | Check catalog integrity, model bounds and TOML consistency; refresh from official CLI metadata |
| `scripts/build.py` | Render URLs/scripts, verify GeoIP, create checksummed bundles |
| `scripts/deploy.py` | Snapshot, publish, activate services, verify, recover |
| Caddy | HTTPS, route allowlists, caching, authentication and request limits |
| `src/mihomo/`, `src/stash/` | Target proxy tools and the server-side text writer |

Claude settings are serialized as JSON; Codex TOML preserves its bytes and comments. Codex checks also cover catalog integrity, selected model/provider, supported reasoning and compaction bounds; they do not replace the full product schema. Shared presets are configurable, and model metadata follows the [catalog policy](../config/codex/README.md). Both client files are public; credentials, project trust and UI history are excluded. The catalog filename resolves beside `config.toml`. The wizard expands user-home input paths before saving so sudo does not redirect them. Release metadata excludes operator input paths and stash tokens.

## Public routes

| Route | Behavior |
| --- | --- |
| `/` | Configured title and filing footer |
| `/ssh/<ssh_public_key_name>` | Public key under the configured filename; default `key.pub` |
| `/mihomo/install`, `/mihomo/sub`, `/mihomo/restart` | Self-contained target scripts |
| `/mihomo/assets/geoip-<sha256>.dat` | Pinned data, immutable caching |
| `/claude/install` | 302 to `https://claude.ai/install.sh` |
| `/claude/config` | Public JSON as plain text |
| `/codex/install` | 302 to `https://chatgpt.com/codex/install.sh` |
| `/codex/config` | Public TOML as plain text |
| `/codex/models_1m` | JSON model catalog as plain text |
| `/stash/upload0` … `/stash/upload7` | Upload clients |
| `/stash/download0` … `/stash/download7` | Public GET/HEAD; authenticated PUT replaces content |
| `/stash/upload`, `/stash/download` | Channel-0 aliases |
| `/stash/clear` | GET serves the client; authenticated POST clears all channels |

Unknown routes return 404. Public text uses `no-store` and `nosniff`. Claude and Codex installers remain upstream; the site neither mirrors nor pins them.

## State and isolation

Caddy reads static files through `/srv/linspace/current` and stash data from `/var/lib/stashd`. Authenticated writes pass through a Unix socket to `stashd`, a dedicated systemd account with no TCP listener. Atomic file replacement prevents partial reads; clearing eight files is sequential, not transactional against concurrent uploads. There is no history, expiry, or rate limit.

A deployment lock protects activation and rollback. Immutable public files switch through a symlink; snapshots cover managed configuration, token, service code/units, and the previous pointer. Channel data is independent. Paths and recovery limits: [deployment](deployment.md).
