# Testing

## Offline checks

From the repository root:

```sh
./linspace check
```

The suite checks source and generated-script syntax, documentation links, configuration and catalog consistency, CLI behavior, reproducible builds, release integrity, deployment/recovery helpers and the Stash protocol. It uses temporary files and requires local Unix-socket access, but no personal site configuration or root privileges.

## Disposable deployment

Use a dedicated Debian/Ubuntu systemd host with a valid hostname and certificate setup. The test mode permits reserved domains and incomplete filing fields:

```sh
./linspace configure --config local/site.test.json --internal-test
./linspace deploy --config local/site.test.json --internal-test --dry-run
sudo ./linspace deploy --config local/site.test.json --internal-test --local
./linspace verify --config local/site.test.json --internal-test --local
```

`--internal-test` changes configuration validation only. `--local` directs verification to loopback while checking the configured hostname and TLS certificate. Neither option disables TLS validation or proves public availability. Reserved domains work for offline builds; live HTTPS still needs a valid certificate setup.

For a test bundle, run `sudo bash linspace --internal-test --local` and `python3 verify.py --local` in its extracted directory. Use `--adopt-existing` only for the supported legacy single-site layout described in [Deployment](deployment.md#existing-caddy).

## Release validation

| Area | Verify |
| --- | --- |
| Deployment | First deployment, repeat deployment, rollback, unrelated-site preservation and public HTTPS |
| SSH | Default/custom filenames, disabled publishing, downloaded fingerprint, account import and login with the matching private key |
| Mihomo | Install, valid/invalid subscription, restart, configuration preservation and verified HTTPS through the proxy |
| Claude Code | Official installer, configuration backup/replacement and intended authentication method |
| Codex | Official installer, TOML/catalog compatibility, relative paths from an unrelated working directory and intended authentication method |
| Stash | All channels, aliases, UTF-8/size/authentication boundaries, clear and restoration of initial data |

Use isolated client accounts, including a non-root account with spaces in its home path. Compare source and deployed file hashes. For Codex, validate the selected CLI version and confirm the provider supports the requested models and context limits.

Record the tested revision, runtime versions, network route, injected failures and skipped checks in release records. A successful catalog load does not prove provider capacity; a loopback check does not prove public reachability. Preserve existing data, and remove only test-created files, accounts and credentials afterward.

Production deployment uses issued site details and successful public verification without test flags. See the [deployment workflow](../README.md#deploy).
