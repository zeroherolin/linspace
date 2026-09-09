# linspace deployment release

This bundle is configured for the domain and homepage recorded in `release.json`.
It contains public files, service definitions, Caddy configuration, and its own
deployment and verification tools. No checkout, third-party Python packages, or build tool
is required on the web host. Python 3.9+, Bash, and a Debian 12+ or Ubuntu 22.04+
host running systemd are required. An existing Caddy must be version 2.10 or later. Missing Caddy and runtime tools are installed by the
installer from the official Caddy stable apt repository.

Verify the archive against a checksum received through your trusted release
channel, then extract into a new directory. Run the following from the extracted
`linspace-site` directory; omit sudo when already root:

```sh
sha256sum --check SHA256SUMS
bash linspace --dry-run
sudo bash linspace
```

The domain must already resolve to this host, its filing details must be
complete, and TCP ports 80/443 must be reachable. The installer preserves other
Caddy site blocks, saves a backup under `/var/backups/linspace/`, publishes an
immutable release under `/srv/linspace/releases/`, switches the `current`
symlink, installs stashd, validates and reloads services, and checks HTTPS.
An existing stash token and all channel contents are preserved. New tokens are
saved to `/etc/linspace/stash-token` with mode 0600; they are never included in
this bundle or printed by the installer.

Useful commands from this directory:

```sh
python3 verify.py                       # passive public HTTPS checks
python3 verify.py --local               # loopback HTTPS checks
sudo bash linspace --rotate-token       # explicit token rotation
sudo bash linspace --rollback /var/backups/linspace/BACKUP_NAME
```

A failure during managed-file/service installation triggers an attempted restore;
if recovery fails, the backup path is retained for manual repair. Missing
packages or a newly created service account are not uninstalled during restore.
If installation succeeds but public HTTPS is not ready, the installation is
retained: fix DNS/firewall/certificate issuance and rerun verification.
Rollback also restores the previous token and code, but leaves stash channel
data unchanged. Reconfigure and rebuild in the source repository to change the
domain, homepage, public key, or shared settings; rollback does not edit the
source checkout's local configuration. Keep extra files, editor backups, and
logs outside this extracted directory: the manifest rejects unlisted files.
Do not edit built bundles.

An internal-test release is marked in `release.json` and requires an explicit
`--internal-test` deployment flag. On an internal host with a valid certificate,
`sudo bash linspace --internal-test --local` runs loopback HTTPS verification.
That flag does not waive production filing requirements or TLS validation.
