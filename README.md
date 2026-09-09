# linspace

Deploy a small HTTPS site on your own domain to publish an SSH public key, mihomo management scripts, a Claude Code installation link and shared settings, and eight public text stash channels.

**Configure once, then deploy with one command.** The project generates the homepage, Caddy configuration, and all client URLs from the same configuration. The production workflow assumes your domain is already resolved to the server and its ICP filing is complete.

## What you need

- A Debian 12+ or Ubuntu 22.04+ server running systemd, with root or sudo access.
- Python 3.9+, Git, Bash, curl, and OpenSSH client tools. No pip packages, Node.js, Docker, or database are needed for deployment.
- Your domain, approved website name, and complete ICP filing number, including a suffix such as `-1`.
- Public TCP ports **80 and 443** available to Caddy. Configure both the cloud security group and the server firewall. SSH access must remain available.
- Outbound access to the Debian/Ubuntu and official Caddy package repositories, and certificate authorities.
- Optionally, the SSH **public** key you want to publish. The project ships no personal key. Shared Claude settings default to `{}`, which adds no user-level overrides. Applying a downloaded settings file replaces the client's existing `settings.json`; review or merge it before replacing personal preferences.

One installation manages one domain on a host. A subdomain such as `tools.your-domain.cn` is supported; wildcards, URL paths, custom ports, and multiple independent installations on the same host are not supported by the deployment tool.

## 1. Check domain resolution and filing details

In the domain's DNS provider console, make sure the record points to this server:

| Your chosen domain | Type | Host/name | Value |
| --- | --- | --- | --- |
| `your-domain.cn` | A | `@` | Server's public IPv4 address |
| `tools.your-domain.cn` | A | `tools` | Server's public IPv4 address |

Choose the row that matches the hostname you will deploy. Publish an AAAA record only if this server has working public IPv6; remove an obsolete AAAA record. The tool does not change DNS or add a `www` alias.

Confirm DNS from the deployment machine, replacing the example:

```sh
getent ahosts your-domain.cn
```

If another web server already occupies ports 80/443, resolve that conflict before deploying. Existing Caddy sites can coexist: the installer adds one managed import and preserves other site blocks. If the chosen domain already has an unmanaged Caddy block, follow [existing-site adoption](docs/deployment.md#existing-caddy-installations).

Caddy obtains and renews HTTPS certificates automatically once the hostname and network prerequisites are satisfied. See the [official automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https#overview).

## 2. Install prerequisites and clone

As a user with sudo access:

```sh
sudo apt-get update
sudo apt-get install -y git python3 curl ca-certificates openssh-client

git clone https://github.com/zeroherolin/linspace.git
cd linspace
```

For a root session, omit `sudo`. Keep the checkout outside `/srv/linspace`, which is reserved for generated public releases. Run the remaining `./linspace` and `make` commands from the repository root. The linked client guides identify which commands run on a target machine instead.

## 3. Configure your site

```sh
./linspace configure
```

The wizard asks for:

| Field | What to enter |
| --- | --- |
| Domain | Your already-resolved, ICP-filed hostname, for example `tools.your-domain.cn`. Do not include `https://`, a port, or a trailing slash. |
| Registered website name | The exact name to display in the page title and heading. |
| ICP filing number | Your full issued number, including the site suffix. |
| SSH public key file | A local `.pub` file path, or leave empty to disable the public-key endpoint. Private keys are rejected. |
| Public Claude settings file | Press Enter for `config/claude/settings.json`, which contains `{}`, or provide your own credential-free JSON settings file. |

The wizard saves `local/site.json` and copies a selected public key to `local/ssh.pub`. The entire `local/` directory is ignored by Git. Domain names and required filing fields are validated, and homepage text is HTML-escaped. The tool checks input format, not the registration authority's records.

You can rerun the wizard (Enter keeps an existing value; enter `-` at the SSH-key prompt to disable it), or edit this one file:

```json
{
  "domain": "tools.your-domain.cn",
  "site_name": "Your approved website name",
  "icp_number": "YOUR_COMPLETE_ISSUED_ICP_NUMBER",
  "ssh_public_key_file": "local/ssh.pub",
  "claude_settings_file": "config/claude/settings.json"
}
```

Replace the examples with your actual details. Production builds reject empty filing details and recognized placeholders. Use `"ssh_public_key_file": ""` to disable key publishing. Relative file paths are resolved from the repository root; absolute paths are supported. Use repository-relative paths or explicit absolute paths in saved configuration, rather than `~/` paths whose meaning can change under `sudo`. Put custom settings in `local/` to keep `git pull` straightforward.

`local/site.json` is the default configuration. To select another JSON file, pass `--config local/another-site.json` consistently to `configure`, `build`, `deploy`, `verify`, and `urls`. The wizard always copies a selected key to `local/ssh.pub`; profiles that need different keys should reference separate public-key files when edited manually.

**You do not edit Caddyfiles or search-and-replace domain names in scripts.** The domain in `local/site.json` supplies every generated site URL. View the resulting URLs with:

```sh
./linspace urls
```

## 4. Preview and deploy

Preview the chosen domain and managed locations:

```sh
./linspace deploy --dry-run
```

This checks configuration, asset hashes, template expansion, and the generated release manifest in a temporary directory, then prints the deployment plan. It does not install packages or modify host services. Shell syntax and the host Caddy/systemd configuration are checked during real deployment; `make check` provides the broader offline development checks. Use `./linspace build` if you want a persistent `dist/` bundle to inspect. Then deploy:

```sh
sudo ./linspace deploy
```

The command performs the full sequence:

1. Validates site settings, the pinned GeoIP asset, generated scripts, and release checksums.
2. Installs Caddy from its official stable apt repository if absent, plus missing runtime tools. An existing Caddy installation must be version 2.10 or later.
3. Backs up managed Caddy configuration, the token, service code/units, and previous release pointer under `/var/backups/linspace/`.
4. Publishes the homepage, selected public key, mihomo scripts/data, Claude settings, and stash client scripts into an immutable release directory.
5. Switches `/srv/linspace/current`, installs the dedicated stash account and socket-activated service, and creates the managed Caddy site import.
6. Creates a stash token on first installation, or preserves the existing token on update. Channel contents are preserved.
7. Validates Caddy and systemd configuration, starts/reloads services, and checks public HTTPS. Certificate issuance may take a short time.

A successful run ends with `HTTPS verification passed`. There is no separate archive extraction, manual public-file copying, Caddy editing, or homepage publication step.

If managed-file installation or service activation fails, the command attempts to restore the saved files and previous release. Packages installed and a newly created service account remain installed. If installation succeeds but public HTTPS is not ready, it retains the valid installation and exits with a clear error; correct DNS/firewall/certificate issues, then rerun verification. Details: [deployment and recovery](docs/deployment.md).

## 5. Save the stash token and verify

On a fresh installation, retrieve the token on the server:

```sh
sudo cat /etc/linspace/stash-token
```

Save it in a password manager. The file is root-only (0600), the installer never prints the token, and Caddy stores only its bcrypt hash. An adopted older deployment may have only the existing hash; keep its previous token or explicitly rotate it to create the new token file.

Check the site and services:

```sh
./linspace verify
sudo systemctl is-active caddy stashd.socket
```

Verification checks the homepage, published scripts, headers, redirects, unknown routes, and write authentication. **It does not upload, overwrite, or clear stash content.** To inspect a local TLS/certificate issue:

```sh
./linspace verify --local
sudo journalctl -u caddy -n 80 --no-pager
sudo journalctl -u stashd.service -u stashd.socket -n 80 --no-pager
```

`--local` connects to loopback while retaining normal TLS certificate validation. It is a diagnostic, not a substitute for public verification.

## Use the deployed site

Run client commands on the machine/account that should use the feature. Copy your exact URLs from `./linspace urls`.

| Feature | Guide | Behavior |
| --- | --- | --- |
| SSH key | [SSH](docs/usage/ssh.md) | Publish a key for users to verify and add to their accounts. Deployment does not change the server's own authorized keys. |
| mihomo | [mihomo](docs/usage/mihomo.md) | Install the pinned proxy on a Debian/Ubuntu target; import private nodes locally; restart manually after reboot. Deployment only publishes these tools. |
| Claude Code | [Claude Code](docs/usage/claude.md) | Official installer redirect and a public, credential-free settings file. |
| Text stash | [Stash](docs/usage/stash.md) | Eight channels; token-authenticated writes, public reads, UTF-8 only, at most 1 MiB per channel. |

Stash content has fixed public URLs, no history, and no automatic expiration. Never upload secrets or private data. Keep subscription URLs, node credentials, SSH private keys, and Claude credentials outside Git and the public release directories.

## Update, reconfigure, and recover

Update code and redeploy with the same local configuration:

```sh
git status --short
git pull --ff-only
sudo ./linspace deploy
```

Review and resolve source edits or conflicting untracked files before pulling; deployment-specific `local/` files remain ignored.

Change the domain, site name, filing number, public key, or shared settings through `./linspace configure`, then redeploy. For a domain change, complete its DNS and filing setup first. The managed site switches to the new hostname; Caddy requests its certificate. Channel contents and the token remain unchanged.

Rotate the write token explicitly:

```sh
sudo ./linspace deploy --rotate-token
sudo cat /etc/linspace/stash-token
```

Restore a specific backup printed by a previous deployment:

```sh
sudo ./linspace rollback /var/backups/linspace/BACKUP_NAME
```

Rollback restores managed configuration, the previous token file/hash, service code/units, and the public release pointer. It does not rewind channel contents or the configuration and input files in your checkout. Before deploying again after rollback, make sure your selected local configuration represents the version you intend to publish. Releases and backups are retained for deliberate review and cleanup. See [operations](docs/operations.md) for their locations and recovery details.

## Build elsewhere or develop

```sh
./linspace build        # Requires your configured site; writes dist/
make check              # Offline checks with isolated test settings; no personal config needed
```

`make check` requires Make and OpenSSH client tools in addition to Python and Bash. Install Make with `sudo apt-get install -y make` if needed. Development checks work on macOS and Linux.

The build produces `dist/linspace-site.tar.gz`, a complete self-contained server deployment bundle, and `dist/linspace-mihomo-target.tar.gz`, a target-side proxy bundle. Both have generated SHA256 manifests. The server bundle includes its own deployment tool and readme; see [bundle deployment](docs/deployment.md#deploy-a-built-bundle).

| Directory | Purpose |
| --- | --- |
| `config/` | Site schema, neutral Claude defaults, homepage/Caddy templates |
| `local/` | Your site settings and optional public inputs; ignored by Git |
| `src/` | Modular mihomo and stash implementation |
| `scripts/` | Configuration, build, deployment, verification, and checks |
| `assets/` | Pinned compressed GeoIP snapshot and integrity manifest |
| `tests/` | Configuration, release, deployment/recovery, and protocol tests |
| `dist/` | Disposable generated releases and archives; ignored by Git |

Architecture: [docs/architecture.md](docs/architecture.md). Contributor workflow and internal testing: [CONTRIBUTING.md](CONTRIBUTING.md). The project uses the [MIT license](LICENSE); [GeoIP data notes](assets/README.md) describe the separately bundled third-party snapshot.
