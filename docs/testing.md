# Testing

## Offline checks

From the repository root:

```sh
./linspace check
```

The suite checks syntax, documentation links and anchors, configuration, catalog consistency, CLI behavior, reproducible builds, release integrity, recovery and Stash authentication.

It needs curl, OpenSSL, OpenSSH, local Unix sockets and loopback TCP. Client tests use temporary homes, synthetic keys, an isolated agent and a temporary HTTPS certificate. No personal configuration or root privileges are needed. Linux is the primary client target; test macOS in temporary HOME, CODEX_HOME and XDG directories. Never load real credentials or modify shell profiles, and remove test directories, caches and child processes afterward.

Status messages use `STEP`, `OK`, `INFO`, `WARN` and `ERROR` on stderr. Colors are limited to interactive terminals and can be disabled with `NO_COLOR=1`. URL lists and PID queries remain plain stdout.

## Disposable deployment

Use a dedicated Debian/Ubuntu systemd host with working certificate setup:

```sh
./linspace configure --config local/site.test.json --internal-test
./linspace deploy --config local/site.test.json --internal-test --dry-run
sudo ./linspace deploy --config local/site.test.json --internal-test --local
./linspace verify --config local/site.test.json --internal-test --local
```

`--internal-test` permits reserved domains and incomplete filing fields; it changes validation only. `--local` verifies loopback using the configured hostname and normal TLS checks. Neither flag proves public availability or makes a deployed site private.

Test bundles also require `--internal-test`. Production uses issued site details and public verification without test flags. [Deployment](../README.md#deploy).

## Release validation

| Area | Check |
| --- | --- |
| Deployment | First and repeat deployment, rollback, other-site preservation, public HTTPS |
| SSH | Custom/default names, disabled publishing, fingerprint, import and actual login |
| Mihomo | Install, valid/invalid subscriptions, restart, preserved settings and verified proxy HTTPS |
| Claude Code | Installer, configuration replacement and intended login method |
| Codex | Installer, TOML/catalog compatibility, relative paths, auth backup/permissions/failure handling |
| Stash | All channels and aliases, file/agent key discovery, replay/tamper rejection, clear and preserved data |

Test non-root accounts and paths containing spaces. Compare source and published hashes. Exercise Codex's hidden token prompt, `-t`, optional `-u`, unchanged configuration without `-u`, and failed-write recovery with synthetic credentials. A stored login does not prove provider access or context capacity.

Record the revision, runtimes, network route, failures and skipped checks. Restore initial data and remove test-created files, accounts and credentials. A loopback success alone does not prove public reachability.
