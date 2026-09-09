# Deployment and recovery

The complete first-time procedure is in the [README](../README.md). Production requires a resolved, ICP-filed domain, its registered site name and number, and a Debian/Ubuntu systemd host. Domain and homepage values live in the selected site JSON (`local/site.json` by default, or a file selected with `--config`). The builder renders all public URLs and Caddy configuration from that file. Commands below run from the repository root unless the bundle section says otherwise.

## Existing Caddy installations

The installer manages `/etc/caddy/sites-enabled/linspace.caddy` and adds this top-level line to `/etc/caddy/Caddyfile`:

```caddy
import /etc/caddy/sites-enabled/linspace.caddy
```

Other site blocks and global options are preserved. An existing top-level import glob that already includes the managed file is reused, so the site is not imported twice. A reserved site file without managed state is rejected for inspection before it can be overwritten. On a fresh host where the installer just installed Caddy, it replaces the package's welcome-site configuration with the managed import. The previous configuration is included in the backup.

If the chosen domain already has an unmanaged site block, deployment stops rather than creating a duplicate. The previous linspace layout, consisting of a single domain block rooted at `/srv/linspace`, can be adopted explicitly:

```sh
sudo ./linspace deploy --adopt-existing
```

This option accepts only that single-site layout. For a shared or more complex configuration, remove/merge the old block yourself while preserving other sites, then use the managed import. Caddy validation catches conflicting addresses and configuration errors before reload.

An older installation's bcrypt hash is retained. If there is no plaintext token at `/etc/linspace/stash-token`, continue using the old token from your password manager. To issue a new one and save it at the standard path, deploy with `--rotate-token`.

## Managed locations

| Location | Purpose |
| --- | --- |
| `/srv/linspace/releases/<id>/` | Immutable public files, directories 0755 and files 0644 |
| `/srv/linspace/current` | Symlink to the active public release |
| `/etc/caddy/sites-enabled/linspace.caddy` | Generated domain site block |
| `/etc/caddy/linspace.d/stash.caddy` | Stash routes and bcrypt hash, root:caddy 0640 |
| `/etc/linspace/stash-token` | New plaintext token, root-only 0600 in a 0700 directory |
| `/usr/local/lib/stashd/stashd.py` | Root-owned writer code |
| `/etc/systemd/system/stashd.socket` and `/etc/systemd/system/stashd.service` | Socket activation and service isolation |
| `/run/stashd/stashd.sock` | Unix write transport, stash:caddy 0660 |
| `/var/lib/stashd/` | Channel contents, preserved across deployment and rollback |
| `/var/lib/linspace/state.json` | Active release metadata and last backup, root-only |
| `/var/backups/linspace/<timestamp>/` | Configuration, token, code/unit snapshots, and previous release pointer |

Static project files are served from the active release directory; stash channel reads are served separately from `/var/lib/stashd`. Source repositories, backups, token files, service code, and deployment tools are outside both public data locations. Unlisted URL paths return 404.

## Deployment stages and failures

The deploy command rebuilds from current configuration, validates checksums and script syntax, installs missing dependencies, acquires a deployment lock, and snapshots managed state. It stages an immutable public release, prepares Caddy/service files, switches the release symlink, validates Caddy and systemd definitions, activates stashd, reloads Caddy, and then verifies HTTPS.

A single symlink switch selects the complete public file set. Service/configuration changes are not a whole-host transaction: on a failure, the deployer attempts to restore the saved managed files, token, code, and symlink. It retains the backup path if that recovery itself fails. It does not uninstall newly added packages/accounts or restore arbitrary unrelated host state.

Caddy may need time to obtain certificates. If the installation is valid but HTTPS verification fails, the installed state remains available for diagnosis. Correct the reported DNS, port, or certificate issue and run `./linspace verify`; do not repeatedly rotate tokens or delete certificate storage.

`./linspace deploy --dry-run` checks configuration, asset integrity, template expansion, and the release manifest, then prints the chosen domain/paths. It does not perform the later shell, Caddy, or systemd validation steps, prove DNS reachability, or install packages. Deployment builds in temporary storage so sudo does not leave root-owned output in your checkout. `--skip-verify` explicitly skips the final network check; use it only when a separate verification step is planned, and do not report the site ready until that check passes.

## Deploy a built bundle

Build on a machine with Python 3.9+, using the desired site configuration:

```sh
./linspace build
awk '$2 == "linspace-site.tar.gz" { print }' dist/SHA256SUMS > dist/linspace-site.tar.gz.sha256
```

Transfer both `dist/linspace-site.tar.gz` and `dist/linspace-site.tar.gz.sha256` through your trusted deployment channel. On the web host, start in the directory holding those two files, then verify and extract into a new directory:

```sh
sha256sum --check linspace-site.tar.gz.sha256
release_dir=$(mktemp -d ./linspace-release.XXXXXX)
tar --no-same-owner -xzf linspace-site.tar.gz -C "$release_dir"
cd "$release_dir/linspace-site"
sha256sum --check SHA256SUMS
bash linspace --dry-run
sudo bash linspace
```

The bundle already contains configured public files and the deployment tools; no Git checkout, pip installation, or build step is needed on the server. Use `python3 verify.py` for its passive HTTPS checks. Reconfigure/rebuild in the source repository for content/domain changes; editing a bundle invalidates its manifest. Keep logs, editor backups, and additional files outside the extracted bundle, because its integrity check also rejects unlisted files. A checksum checks bytes against the value you received; obtain that checksum through the same trusted release process.

## Rollback

Use an exact direct child directory of `/var/backups/linspace`:

```sh
sudo ./linspace rollback /var/backups/linspace/BACKUP_NAME
```

A bundle provides the same operation as `sudo bash linspace --rollback /var/backups/linspace/BACKUP_NAME`. The backup is root-only because it may contain the previous token. A rollback can restore a previous domain and invalidate a rotated token by restoring the old one. Channel data remains current. Rollback does not update `local/site.json`, public-key inputs, or custom settings files in your checkout. A later deployment rebuilds from those inputs, so review them before redeploying.

## Reference implementation choices

Caddy installation follows its [official Debian/Ubuntu package instructions](https://caddyserver.com/docs/install#debian-ubuntu-raspbian). Site integration uses [Caddy imports](https://caddyserver.com/docs/caddyfile/directives/import); reload is preceded by [configuration validation](https://caddyserver.com/docs/command-line#caddy-validate). The standard Caddy systemd service owns certificate persistence and renewal.
