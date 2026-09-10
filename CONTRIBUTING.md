# Contributing

## Local checks

Use Python 3.9+, Bash, curl, OpenSSL and OpenSSH 8.2+. Pinned Python parsers are bundled; no pip installation is required.

```sh
./linspace check
```

To select a Python interpreter:

```sh
make check PYTHON=python3.12
```

Checks need local Unix sockets and loopback HTTPS, but no personal configuration or root access. CI uses Python 3.9 and 3.12. [Testing details](docs/testing.md).

## Source conventions

Edit `src/`, `scripts/`, `config/`, `docs/` and `packaging/`; do not edit generated `dist/`. Keep operator-specific inputs in ignored `local/`.

- Preserve feature order: **SSH → Mihomo → Claude Code → Codex → Stash**.
- Add routes, passive verification, behavior tests and usage documentation for new endpoints.
- Keep credentials, machine-specific paths, project trust and UI history out of public presets.
- Use relative paths for companion client files.
- Write English user guides with short, standalone commands. Keep loops, functions and recovery logic in tools, not copy-and-paste setup blocks.
- Keep private deployment details and session history outside the repository.

Templates support `@@include:src/component/file@@`, `@@DOMAIN@@` and `@@GEO_SHA@@`. Avoid conflicting heredoc delimiters. When changing configuration fields, cover both new and existing profiles. Check Markdown links, anchors and shell examples.

## Versions and release validation

Download versions and hashes come from `config/downloads.json`; validate Mihomo API behavior when changing its version. This manifest is the only interface to download hosting. Import a verified export from the resource project before deploying. Keep bundled parser code and notices in `vendor/` consistent with their manifest.

Update the Codex catalog through its [refresh procedure](config/codex/README.md#refresh-and-validate). Normal builds need neither Codex nor network access.

Identical inputs produce identical archives within the same Python/zlib runtime. Publish checksums for the actual archives. Complete [release validation](docs/testing.md#release-validation) before publishing; local checks do not prove public connectivity or provider access.
