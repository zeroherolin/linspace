# Contributing

## Local checks

Use Python 3.9+, Bash and OpenSSH client tools. Python 3.11+ includes the TOML parser. Older versions need `python3-tomli` on Debian/Ubuntu, or `python -m pip install -r requirements.txt` inside a virtual environment.

```sh
./linspace check
# With Make and a selected interpreter:
make check PYTHON=python3.12
```

Checks need no personal configuration or root access. The Stash tests require local Unix sockets. CI runs on Python 3.9 and 3.12. See [Testing](docs/testing.md) for coverage and live release checks.

## Source conventions

- `config/`: public presets, schema and templates.
- `src/`: runtime implementation.
- `scripts/`: configuration, build, deployment and checks.
- `docs/`: user and maintainer guides.
- `packaging/`: bundle README templates.

Edit source files, not generated `dist/`. Keep deployment-specific values in ignored `local/`.

Use the feature order **SSH → Mihomo → Claude Code → Codex → Stash** throughout commands and documentation. New endpoints need an explicit Caddy route, passive verification, behavior tests and a usage guide. Shared presets must not contain credentials, project trust, UI history or machine-specific paths. Companion client files use relative paths.

Documentation describes the current project and reproducible procedures. Keep private hostnames, personal endpoint names, development-session narratives and one-off deployment results outside the repository. Use generic examples; preserve required attribution and authoritative upstream references.

Templates expand `@@include:src/component/file@@`, `@@DOMAIN@@` and `@@GEO_SHA@@`. Avoid conflicting heredoc delimiters. When adding configuration fields, test both new and existing profiles. Check Markdown links, heading anchors and command examples.

## Versions and release validation

Mihomo is pinned to v1.19.27. Update engine checksums and runtime expectations in install/process/sub together. GeoIP is defined in `assets/manifest.json`; review provenance and licensing before replacing it. Claude Code and Codex installer routes follow official upstream URLs.

Refresh the Codex catalog with `python3 scripts/codex_catalog.py --refresh` using a reviewed official CLI. Review both model entries and their [source record](config/codex/README.md). Normal builds require neither Codex nor network access.

Identical inputs produce identical archives within the same Python/zlib runtime. Distribute the checksum for the actual archive. Complete the [release checks](docs/testing.md#release-validation) before publishing; local tests do not establish public TLS, authentication or provider capacity.
