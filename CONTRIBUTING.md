# Contributing

## Checks

Use Python 3.9+, Bash, curl, OpenSSL and OpenSSH 8.2+. Parsers are bundled in `vendor/`; no pip installation is required.

```sh
./linspace check
```

Or `make check PYTHON=python3.12` to select an interpreter. The suite checks syntax, Markdown links and anchors, configuration validation, catalog consistency, CLI behavior, reproducible builds, release integrity, the rendered help pages, deployment locking, rollback, Stash authentication and client lifecycle behavior. It needs local Unix sockets and loopback HTTPS but no personal configuration or root access. Tests use temporary homes, synthetic keys, an isolated agent and a temporary certificate; they never load real credentials, modify shell profiles or inspect personal clients. CI runs Python 3.9 and 3.12.

Status messages use `STEP`, `OK`, `INFO`, `WARN` and `ERROR` on stderr; colors appear only on interactive terminals and can be disabled with `NO_COLOR=1`. URL lists and PID queries stay on stdout.

## Source conventions

Edit `src/`, `scripts/`, `config/` and `docs/`; never edit generated `dist/`. Keep operator inputs in ignored `local/`.

- Preserve feature order: **SSH → Mihomo → tmux → Claude Code → Codex → Stash**.
- Add routes, passive verification, behavior tests and documentation together for new endpoints.
- Keep credentials, machine-specific paths, project trust and UI history out of public presets. Use relative paths for companion client files.
- Write English guides with short, standalone commands. Keep loops, functions and recovery logic in tools, not in copy-and-paste setup blocks.
- `docs/help.md` and `docs/help2.md` use only the Markdown subset rendered by `scripts/helppage.py`: headings, paragraphs, lists, inline and fenced code. Write shared sections once in `docs/help.md` and include them in `docs/help2.md` with `@@include:docs/help.md#Heading@@`.
- Keep lifecycle behavior in `src/lifecycle/`. Reuse existing installations; never remove desktop bundles, shared runtimes or unrelated processes. Uninstall keeps only session records (`clients.Client.RETAINED`) and removes credentials and user extensions. Successful client operations retain no backups.
- Keep private deployment details and session history outside the repository.

Templates support `@@include:src/component/file@@`, `@@DOMAIN@@`, `@@ALIAS_BLOCK@@` (Caddyfile only) and `@@GEO_SHA@@`. Client scripts and public files embed only the canonical domain; aliases appear solely in the Caddy redirect block and `release.json`. Avoid conflicting heredoc delimiters. When changing configuration fields, cover both new and existing profiles.

## Versions and dependencies

Download versions and hashes come from `config/downloads.json`, exported from the separate resource project; it is the only interface to download hosting. Validate Mihomo API behavior when changing its version. Update the Codex catalog with `python3 scripts/codex_catalog.py --refresh` from a reviewed CLI version ([policy](docs/architecture.md#codex-preset-and-catalog)); normal builds need neither Codex nor network access.

`vendor/manifest.json` records the bundled `tomli` and PyYAML versions and checksums; each ZIP contains only runtime code and its MIT license. `vendor/notices/` holds licenses shipped with downloaded programs. Update these as a reviewed bundle without editing upstream code or removing notices.

## Release validation

Identical inputs produce identical archives within the same Python/zlib runtime; publish checksums for the actual archives. Before publishing, validate on a disposable Debian/Ubuntu host:

```sh
./linspace configure --config local/site.test.json --internal-test
sudo ./linspace deploy --config local/site.test.json --internal-test --local
./linspace verify --config local/site.test.json --internal-test --local
```

`--internal-test` permits reserved domains and incomplete filing fields; `--local` verifies loopback. Neither proves public availability.

| Area | Check |
| --- | --- |
| Deployment | First and repeat deployment, rollback, other-site preservation, public HTTPS |
| SSH | Custom and default names, disabled publishing, fingerprint, import and actual login |
| Mihomo | Install, subscriptions, restart, verified proxy HTTPS, uninstall and reinstall |
| tmux | Existing-version reuse, Linux package-manager install, macOS Homebrew install, configuration publishing |
| Claude Code | Native/npm coexistence, reuse, uninstall with session-record retention and reinstall |
| Codex | Native/npm coexistence, reuse, catalog/auth compatibility, prompt and `-t`/`-u` paths, failed-write recovery, uninstall with session-record retention and reinstall |
| Stash | All channels and aliases, file/agent key discovery, replay/tamper rejection, clear and preserved data |

Test non-root accounts and paths containing spaces. Exercise uninstall and real process stopping only in disposable Linux containers; macOS tests use temporary homes and mocked process results. Apple Silicon installs real pinned packages; Intel coverage checks asset selection and needs an Intel Mac for final validation. Record the revision, runtimes, network route, failures and skipped checks, then remove test-created files, accounts and credentials.
