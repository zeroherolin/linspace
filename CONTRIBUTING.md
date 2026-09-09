# Contributing

Run `make check` before review. It builds with isolated test settings and checks source syntax, rendered scripts, links, release integrity, configuration validation, Caddy-file integration/rollback helpers, and the stash writer protocol. No personal configuration or root privileges are needed. The stash protocol tests bind a temporary Unix socket; the test environment must allow that local IPC operation. Python 3.9+, Bash, Make, and OpenSSH client tools are the local dependencies.

## Source layout

Edit `src/` for runtime behavior, `config/` for schema/defaults/templates, `scripts/` for tooling, and `docs/` for guides. Never edit generated `dist/` files. The Markdown files under `packaging/` are release-readme templates; edit them there and rebuild to update extracted bundles and archives together. Deployment-specific values belong in ignored `local/` files.

Shell templates insert whole source files with `@@include:src/component/file@@`. `@@DOMAIN@@` and `@@GEO_SHA@@` are substituted at build time. Keep heredoc delimiters out of included files, and ensure newly added public endpoints have an explicit Caddy route. Extend `scripts/verify.py` with passive checks for new endpoints.

The hostname is configuration data, not a source-code constant. Tests build two different domains and check generated URLs, optional key routes, HTML escaping, checksum rejection, and deterministic artifacts. Do not add a personal key, credential, fixed personal domain, or permissive personal Claude settings to defaults.

## Versions and data

The engine remains pinned to mihomo v1.19.27. An upgrade requires reviewing the engine's architecture checksums and all runtime version expectations in `src/mihomo/install.sh.in`, `src/mihomo/process.py`, and `src/mihomo/sub.py`. GeoIP is identified by `assets/manifest.json`; its hash is injected into the scripts and Caddy asset path. Review upstream data provenance/license when replacing the snapshot.

Build archives have stable ordering, ownership, modes, and timestamps. Within the same Python/zlib runtime, identical inputs generate identical archives. Different compression-library versions can produce different archive hashes for identical extracted files; always transfer the checksum for the actual archive.

## Linux validation

Local tests do not prove actual systemd isolation, certificate issuance, or mihomo behavior. Test deployment, repeat deployment, and recovery on a disposable Debian/Ubuntu systemd host before shipping deployment changes. Verify a non-default domain and ensure unrelated Caddy sites survive. Client changes need a target with real mihomo listeners and valid private nodes; keep test credentials outside Git and logs intended for sharing.

The production README assumes DNS and filing are complete. Maintainer-only pre-filing and loopback workflows are documented separately in [internal testing](docs/internal/testing.md). The historical environment record is in [the internal validation log](docs/internal/validation-2026-09-09.md).

The configurable deployer has a separate [validation record](docs/internal/deployment-v2-validation.md). Validation logs describe the revisions and environments tested at that time; use the current guides for operating commands.

For documentation changes, check heading anchors and fenced command examples as well as local file links. The current `make check` link check covers the main guides and asset readme, checks file existence only, and skips packaging Markdown and heading anchors.
