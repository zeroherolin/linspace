# Architecture

## Layers

| Location | Responsibility |
| --- | --- |
| `config/` and ignored `local/` | Templates, public presets, download manifest and operator inputs |
| `scripts/siteconfig.py` | Domain, alias, filing, public-key and client-setting validation |
| `scripts/codex_catalog.py` | Catalog integrity, consistency and refresh |
| `scripts/helppage.py` | Render `docs/help.md` and `docs/help2.md` into `/help` and `/help2` |
| `scripts/build.py` | Render files and create checksummed bundles |
| `scripts/deploy.py` | Back up, activate, verify and recover |
| Caddy | HTTPS, route allowlists, caching and body limits |
| `src/common/` | Download fallback and terminal output |
| `src/lifecycle/` | Client installation, source discovery, process stopping and uninstall |
| `src/mihomo/` | Client proxy tools |
| `src/tmux/` | tmux package-manager install and removal |
| `src/codex/` | Local API credential setup |
| `src/stash/` | Signed upload clients and the text and page writer |
| `src/page/` | Page-host Caddy block, the page template with the filing notice, and per-name scripts |
| `vendor/` | Bundled `tomli` and PyYAML ZIPs with `manifest.json`, plus third-party notices |

Claude JSON is serialized during build; Codex TOML and the tmux configuration keep their bytes. Help sources support headings, paragraphs, lists, inline and fenced code. `docs/help2.md` pulls shared sections from `docs/help.md` with `@@include:docs/help.md#Heading@@` lines; the build replaces `your-domain.cn`, `page.your-domain.cn` and `your-key.pub`, and drops the SSH or Pages section when no key is published or no page host is configured. Shell blocks get lightweight token highlighting, text is escaped and raw HTML is not passed through. Credentials and operator input paths are excluded from public releases.

## Public routes

All routes except published pages are served on the canonical `domain` only. Every hostname in `alias_domains` answers with a `308` redirect to the same path and query on the canonical domain, and never serves content itself; over HTTP it first redirects to its own HTTPS form. One origin keeps Stash signatures, download URLs and browser storage unambiguous; aliases exist so a filing's `www` form or a legacy hostname keeps working.

| Route | Behavior |
| --- | --- |
| `/` | Site title, help link and filing footer |
| `/help` | Rendered `docs/help.md`: tmux, Claude Code, Codex and their uninstall commands |
| `/help2` | Complete help with SSH, Mihomo, Stash and Pages; not linked from the home page and without the filing footer |
| `/ssh/<ssh_public_key_name>` | Selected public key; default name `key.pub` |
| `/mihomo/install`, `/mihomo/sub`, `/mihomo/restart`, `/mihomo/uninstall` | Client proxy scripts |
| `/tmux/install`, `/tmux/uninstall` | Package-manager installation of tmux 3.2+ and removal with its data |
| `/tmux/config` | Shared `~/.tmux.conf` contents |
| `/claude/install`, `/codex/install` | Installers with verified download fallback |
| `/claude/config` | Public JSON |
| `/codex/config`, `/codex/models_1m` | Public TOML and model catalog |
| `/codex/auth` | Script that writes credentials on the client |
| `/claude/uninstall`, `/codex/uninstall` | Client uninstall scripts |
| `/stash/upload0`–`7` | Upload scripts |
| `/stash/download0`–`7` | Public GET/HEAD; signed PUT replaces content |
| `/stash/upload`, `/stash/download` | Channel-0 aliases |
| `/stash/keys` | Authorized public keys for client discovery |
| `/stash/challenge` | GET issues a signing challenge; HEAD checks availability |
| `/stash/clear` | GET serves the script; signed POST clears all channels |
| `/stash/page/NAME` | Signed PUT publishes a page and signed DELETE removes it; needs `page_domain` |

Unknown routes return 404. Public text is served with `no-store` and `nosniff`. Download-based installer scripts use official sources first and a pinned, verified download fallback; the tmux installer delegates to the host package manager. The build embeds `config/downloads.json`; download hosting requires no installer-code changes.

## Pages

`page_domain` names a second hostname for published HTML. Pages run on that separate origin, so their scripts keep browser storage but cannot reach the site, and no sandbox is needed. Writes go through the canonical domain's signed Stash API; the page host serves only files and never reaches `stashd`.

| Page-host route | Behavior |
| --- | --- |
| `/NAME` | The stored page followed by the filing notice, as `text/html` |
| `/NAME/upload`, `/NAME/delete` | Client scripts with `NAME` filled in |
| `/robots.txt` | Disallows all crawling |
| `/` | `308` redirect to the canonical home page |

`NAME` matches `[a-z0-9][a-z0-9_-]{0,47}`: lowercase avoids names that differ only in case, and underscores are allowed because paths, unlike hostnames, accept them. Script addresses with any other name return a script that states the rule and exits 1, since `curl -f` would hide a 404 body; other paths return 404. Caddy's `templates` handler renders the release's `page/view` and scripts with the delimiters `[[linspace:` and `]]`, one action per file. The view inserts the stored page with `readFile`, which never evaluates it, then appends the filing notice from the active release, so redeploying after an `icp_number` change updates every page. A small script moves the notice after `<body>` when the body is a flex or grid container. Range requests are stripped so the file server cannot return an unrendered template.

Every response carries `no-store`, `nosniff`, `X-Robots-Tag: noindex, nofollow` and `Referrer-Policy: strict-origin-when-cross-origin`, which keeps map tiles and other referrer-checked resources working. Pages may load `https://` resources and cannot be framed by other origins. All pages share one origin and its storage; they all come from authorized keys.

## Codex preset and catalog

| File | Purpose |
| --- | --- |
| `config/codex/config.toml` | Shared model, provider, context and client preferences |
| `config/codex/models-1m.json` | Model entries exported from the official Codex CLI |
| `config/codex/catalog-source.json` | Source version, export hash, overrides and output hash |

Each model keeps its official instructions, capabilities, reasoning choices and service-tier metadata. Only `context_window` (1,000,000), `max_context_window` (1,050,000) and `effective_context_window_percent` (100) are overridden, matching the 1,050,000-token windows documented for [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol). The overrides set the client's budget; they do not grant provider capacity or model access.

The preset compacts at 900,000 tokens, uses `xhigh` reasoning, an OpenAI-compatible relay, `on-request` / `auto_review` approvals and `danger-full-access`. `cli_auth_credentials_store = "file"` keeps API credentials in the client's `auth.json`; credentials are never bundled. Offline checks validate hashes, model IDs, context bounds, reasoning levels and TOML consistency against the [official schema](https://developers.openai.com/codex/config-schema.json), not the complete product schema. Refresh with `python3 scripts/codex_catalog.py --refresh` from a reviewed CLI version, then run `./linspace check`.

The auth script writes `auth.json` with mode `600` through a staged replacement that rolls back on failure and keeps no backup; its prompts and flags are in the [user guide](usage.md#codex).

## Server state

| Path | Purpose |
| --- | --- |
| `/srv/linspace/releases/` | Immutable public releases: directories 0755, files 0644 |
| `/srv/linspace/current` | Active release symlink |
| `/etc/caddy/sites-enabled/linspace.caddy` | Domain, alias and page-host routes |
| `/etc/caddy/linspace.d/stash.caddy` | Stash routes; root:caddy 0640 |
| `/usr/local/lib/stashd/` | Writer code and root-owned `allowed_signers` |
| `/etc/systemd/system/stashd.{socket,service}` | Socket activation and service isolation |
| `/run/stashd/ssh.sock` | Writer socket; stash:caddy 0660 |
| `/var/lib/stashd/` | Public channel data; published pages in `pages/` |
| `/var/lib/linspace/state.json` | Deployment metadata |
| `/var/backups/linspace/` | Configuration, authentication, code, units and release pointer |

Caddy serves only allowlisted paths from `/srv/linspace/current`, channel data from `/var/lib/stashd` and pages from `/var/lib/stashd/pages`. The checkout, backups and service code are outside public roots. The dedicated `stash` account verifies writes through the Unix socket and has no TCP listener. When linspace owns `/etc/caddy/Caddyfile` (a fresh installation or the earlier import-only layout), the file starts with a marker comment and global `servers { timeouts { read_header 10s; read_body 60s } }`; in a shared Caddyfile only the import line is added and the operator keeps control of global options.

Deployment takes a lock, copies the release into an immutable directory, snapshots managed files, activates them and switches the symlink. Rollback restores the snapshot and the previous pointer but not channel contents or pages. Uploads replace files atomically; clearing channels is sequential, not a transaction against concurrent uploads. There is no content history or expiry.

## Stash authentication

Stash uses [OpenSSH SSHSIG signatures](https://man.openbsd.org/ssh-keygen.1#Y~3) over HTTPS. Caddy limits request bodies; `stashd` verifies every write, including direct Unix-socket requests. No SSH login, extra TCP port or shared client token is needed.

1. GET `/stash/keys` returns authorized public keys for client discovery.
2. GET `/stash/challenge` returns an opaque challenge valid for 90 seconds.
3. Sign the message below with namespace `linspace-stash@DOMAIN`.
4. Send PUT `/stash/downloadN` or `/stash/page/NAME` with the file bytes, POST `/stash/clear` with an empty body, or DELETE `/stash/page/NAME` without a body, carrying `X-Linspace-Challenge` and `X-Linspace-Signature` (Base64 of the ASCII-armored signature).

```text
linspace-stash-v1
https://DOMAIN
METHOD
/stash/downloadN
LOWERCASE_SHA256_OF_BODY
CHALLENGE
```

Lines end with LF, including the last. For clear, use `POST`, `/stash/clear` and the empty-body digest; a page deletion signs `DELETE`, its path and the empty-body digest. Page writes are signed for the canonical domain, not the page host. The configured hostname defines the audience, not the request Host header. Write paths reject queries, alternate encodings and absolute-form targets; clients do not follow redirects with signed requests.

The build emits a root-owned `allowed_signers` file for up to 64 keys, restricted to the site's namespace and the `stash` principal; `ssh-keygen -Y verify` checks it. All authorized keys have equal upload and clear access. A challenge holds 32 random bytes, an expiry and an HMAC-SHA256 over a per-process secret; issuance stores nothing. After verification a locked replay map consumes the challenge once. Restarts replace the secret and invalidate old challenges. Clients need no synchronized clock.

| Bound | Limit |
| --- | --- |
| Challenge lifetime | 90 seconds |
| Client signing step | 60 seconds; one automatic retry with a fresh challenge after 401 |
| Used challenges | 8,192; expired entries are removed |
| Concurrent verifications | 4 |
| Verification subprocess | 5 seconds |
| Request body | 60 seconds in total, regardless of transfer speed |
| Body size | 1 MiB for channels, 4 MiB for pages |
| Published pages | 64; a new name beyond that returns 507 |
| Active connections | 32 |

Invalid, expired or replayed authorization returns 401. A body that does not arrive within its deadline returns 408. Exhausted verification capacity returns 429; a full connection table answers 503 with `Retry-After` instead of dropping the connection; transient verification failures return 503. Every response closes its connection, and the Caddy fragment disables upstream keep-alive, so a write is never retried over a stale connection. Legacy Basic authentication is rejected; the SSH writer uses `/run/stashd/ssh.sock`, distinct from the legacy socket, and deployment pauses writes during activation.
