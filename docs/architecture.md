# Architecture

## Layers

| Location | Responsibility |
| --- | --- |
| `config/` and ignored `local/` | Templates, public presets, download manifest and operator inputs |
| `scripts/siteconfig.py` | Domain, filing, public-key and client-setting validation |
| `scripts/codex_catalog.py` | Catalog integrity, consistency and refresh |
| `scripts/helppage.py` | Render `docs/help.md` into the public `/help` page |
| `scripts/build.py` | Render files and create checksummed bundles |
| `scripts/deploy.py` | Back up, activate, verify and recover |
| Caddy | HTTPS, route allowlists, caching and body limits |
| `src/common/` | Download fallback and terminal output |
| `src/lifecycle/` | Client installation, source discovery, process stopping and uninstall |
| `src/mihomo/` | Client proxy tools |
| `src/codex/` | Local API credential setup |
| `src/stash/` | Signed upload clients and the text writer |
| `vendor/` | Bundled `tomli` and PyYAML ZIPs with `manifest.json`, plus third-party notices |

Claude JSON is serialized during build; Codex TOML preserves formatting. `docs/help.md` supports headings, paragraphs, lists, inline and fenced code; text is escaped and raw HTML is not passed through. Credentials and operator input paths are excluded from public releases.

## Public routes

| Route | Behavior |
| --- | --- |
| `/` | Site title, help link and filing footer |
| `/help` | Rendered `docs/help.md` |
| `/ssh/<ssh_public_key_name>` | Selected public key; default name `key.pub` |
| `/mihomo/install`, `/mihomo/sub`, `/mihomo/restart` | Client scripts |
| `/claude/install`, `/codex/install` | Installers with verified download fallback |
| `/claude/config` | Public JSON |
| `/codex/config`, `/codex/models_1m` | Public TOML and model catalog |
| `/codex/auth` | Script that writes credentials on the client |
| `/claude/uninstall`, `/codex/uninstall`, `/mihomo/uninstall` | Client uninstall scripts |
| `/stash/upload0`–`7` | Upload scripts |
| `/stash/download0`–`7` | Public GET/HEAD; signed PUT replaces content |
| `/stash/upload`, `/stash/download` | Channel-0 aliases |
| `/stash/keys` | Authorized public keys for client discovery |
| `/stash/challenge` | GET issues a signing challenge; HEAD checks availability |
| `/stash/clear` | GET serves the script; signed POST clears all channels |

Unknown routes return 404. Public text is served with `no-store` and `nosniff`. Installer scripts use official sources first and a pinned, verified download fallback. The build embeds `config/downloads.json`; download hosting requires no installer-code changes.

## Codex preset and catalog

| File | Purpose |
| --- | --- |
| `config/codex/config.toml` | Shared model, provider, context and client preferences |
| `config/codex/models-1m.json` | Model entries exported from the official Codex CLI |
| `config/codex/catalog-source.json` | Source version, export hash, overrides and output hash |

Each model keeps its official instructions, capabilities, reasoning choices and service-tier metadata. Only `context_window` (1,000,000), `max_context_window` (1,050,000) and `effective_context_window_percent` (100) are overridden, matching the 1,050,000-token windows documented for [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol). The overrides set the client's budget; they do not grant provider capacity or model access.

The preset compacts at 900,000 tokens, uses `xhigh` reasoning, an OpenAI-compatible relay, `on-request` / `auto_review` approvals and `danger-full-access`. `cli_auth_credentials_store = "file"` keeps API credentials in the client's `auth.json`; credentials are never bundled. Offline checks validate hashes, model IDs, context bounds, reasoning levels and TOML consistency against the [official schema](https://developers.openai.com/codex/config-schema.json), not the complete product schema. Refresh with `python3 scripts/codex_catalog.py --refresh` from a reviewed CLI version, then run `./linspace check`.

## Server state

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

Caddy serves only allowlisted paths from `/srv/linspace/current` and channel data from `/var/lib/stashd`. The checkout, backups and service code are outside public roots. The dedicated `stash` account verifies writes through the Unix socket and has no TCP listener.

Deployment takes a lock, copies the release into an immutable directory, snapshots managed files, activates them and switches the symlink. Rollback restores the snapshot and the previous pointer but not channel contents. Uploads replace files atomically; clearing channels is sequential, not a transaction against concurrent uploads. There is no content history or expiry.

The Codex auth script atomically replaces local `auth.json` with mode `600`, without retained backups. Interactively it asks for an optional `base_url` visibly, then reads the token hidden; `-u` skips the URL prompt and `-t` disables all prompts. Both paths share the same validation and staged write with rollback on failure. No credentials are sent to the site or the model provider.

## Stash authentication

Stash uses [OpenSSH SSHSIG signatures](https://man.openbsd.org/ssh-keygen.1#Y~3) over HTTPS. Caddy limits request bodies; `stashd` verifies every write, including direct Unix-socket requests. No SSH login, extra TCP port or shared client token is needed.

1. GET `/stash/keys` returns authorized public keys for client discovery.
2. GET `/stash/challenge` returns an opaque challenge valid for 90 seconds.
3. Sign the message below with namespace `linspace-stash@DOMAIN`.
4. Send PUT `/stash/downloadN` with the file bytes, or POST `/stash/clear` with an empty body, carrying `X-Linspace-Challenge` and `X-Linspace-Signature` (Base64 of the ASCII-armored signature).

```text
linspace-stash-v1
https://DOMAIN
METHOD
/stash/downloadN
LOWERCASE_SHA256_OF_BODY
CHALLENGE
```

Lines end with LF, including the last. For clear, use `POST`, `/stash/clear` and the empty-body digest. The configured hostname defines the audience, not the request Host header. Write paths reject queries, alternate encodings and absolute-form targets; clients do not follow redirects with signed requests.

The build emits a root-owned `allowed_signers` file for up to 64 keys, restricted to the site's namespace and the `stash` principal; `ssh-keygen -Y verify` checks it. All authorized keys have equal upload and clear access. A challenge holds 32 random bytes, an expiry and an HMAC-SHA256 over a per-process secret; issuance stores nothing. After verification a locked replay map consumes the challenge once. Restarts replace the secret and invalidate old challenges. Clients need no synchronized clock.

| Bound | Limit |
| --- | --- |
| Challenge lifetime | 90 seconds |
| Used challenges | 8,192; expired entries are removed |
| Concurrent verifications | 4 |
| Verification subprocess | 5 seconds |
| Active connections | 32 |

Invalid, expired or replayed authorization returns 401. Exhausted capacity returns 429; transient verification failures return 503. Legacy Basic authentication is rejected; the SSH writer uses `/run/stashd/ssh.sock`, distinct from the legacy socket, and deployment pauses writes during activation.
