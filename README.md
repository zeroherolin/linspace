# linspace

A small HTTPS site for SSH keys, Mihomo tools, Claude Code, Codex, and eight public text channels. Configure one domain, then deploy with one command.

## Deploy

Run these steps on the web server. Use Debian 12+ or Ubuntu 22.04+ with systemd and root/sudo access. The production workflow requires an already-resolved, ICP-filed domain and its approved website name and filing number.

### 1. Prepare the domain and network

- Point the domain's A record to this server. For a subdomain, use its label instead of `@`.
- Publish an AAAA record only if this server has working public IPv6.
- Allow TCP **80/443** in both the cloud security group and host firewall; keep SSH available.
- Resolve any existing listener conflict on 80/443. Other Caddy sites can coexist.
- Allow outbound access to package repositories and certificate authorities.

```sh
getent ahosts your-domain.cn
```

Use the exact hostname you want to serve; the project does not configure DNS or add `www`. One installation manages one domain. Existing installations: [deployment](docs/deployment.md#existing-caddy).

### 2. Install prerequisites and clone

```sh
sudo apt-get update
sudo apt-get install -y git python3 python3-tomli curl ca-certificates openssh-client
cd ~
git clone https://github.com/zeroherolin/linspace.git
cd linspace
```

Omit `sudo` as root. Python 3.9+ is supported; `tomli` provides TOML parsing on Python 3.9/3.10. Python 3.11+ has it built in. No Node.js, Docker, or database is needed on the web host.

Run the remaining project commands from this checkout, outside `/srv/linspace`.

### 3. Configure

```sh
./linspace configure
```

The wizard saves ignored `local/site.json`:

| Field | Value |
| --- | --- |
| `domain` | Your hostname, without `https://`, port, or path |
| `site_name` | Approved website name, displayed on the homepage |
| `icp_number` | Complete issued filing number, including the site suffix |
| `ssh_public_key_file` | Local public `.pub` file; empty disables publishing |
| `ssh_public_key_name` | Published filename under `/ssh/`; defaults to `key.pub` |
| `claude_settings_file` | Shared JSON preset: `config/claude/settings.json` |
| `codex_config_file` | Shared TOML preset: `config/codex/config.toml` |

For example, edit the saved file with your actual details:

```json
{
  "domain": "tools.your-domain.cn",
  "site_name": "Your approved website name",
  "icp_number": "YOUR_COMPLETE_ISSUED_ICP_NUMBER",
  "ssh_public_key_file": "local/ssh.pub",
  "ssh_public_key_name": "team.pub",
  "claude_settings_file": "config/claude/settings.json",
  "codex_config_file": "config/codex/config.toml"
}
```

Replace the placeholders before deployment. Production rejects missing or placeholder filing details; validation checks their format, not authority records.

The wizard copies a selected public key to `local/ssh.pub`. Its public URL uses `ssh_public_key_name`: for example, `team.pub` produces `/ssh/team.pub`. Omit the field to use `key.pub`; see [SSH filename rules](docs/usage/ssh.md) for accepted names.

The bundled Claude Code and Codex presets include model, provider, access and interface preferences. Review them before applying: Claude's built-in sandbox is disabled, and Codex uses `danger-full-access` with an OpenAI-compatible provider.

Keep custom settings in `local/` and select them in the wizard. Both client configurations are **published publicly**; exclude credentials and machine-specific state. Existing profiles keep their selected input files. For Codex, download `/codex/models_1m` as `models-1m.json` beside the client's `config.toml`. See the [catalog policy](config/codex/README.md) for model capabilities and 1M context settings.

Relative input paths resolve from the repository root. The wizard expands `~/` for the account running `configure` before saving, so sudo deployment uses the same files. Run the wizard as that account. When editing JSON manually, use repository-relative or absolute paths. Enter keeps an existing wizard value; `-` disables SSH key publishing.

```sh
./linspace urls
```

The selected domain generates every site URL and Caddy route. Use `--config local/other.json` consistently for a separate profile; profiles needing different keys should reference distinct key files.

### 4. Preview and deploy

```sh
./linspace deploy --dry-run
sudo ./linspace deploy
```

The deployer builds and checks the release, installs missing Caddy/runtime packages, backs up managed state, switches the public release, activates services, and verifies HTTPS. Existing Caddy must be 2.10+. Caddy obtains and renews certificates automatically.

The stash token and channel contents survive redeployment. A managed-file or service failure attempts rollback; a final HTTPS failure retains the installation for diagnosis. See [deployment and recovery](docs/deployment.md).

### 5. Save the token and verify

```sh
sudo cat /etc/linspace/stash-token
./linspace verify
sudo systemctl is-active caddy stashd.socket
```

Keep the token in a password manager. It authorizes all eight upload channels and clear; reads are public. Verification does not modify channel data. If public verification fails, use [diagnostics](docs/operations.md#diagnostics); loopback success alone does not establish public reachability.

## Use

Client commands run on the target machine, as the account using each tool. Clients need no Git checkout. Replace `your-domain.cn` in the guides with the domain from `./linspace urls`.

| Feature | Public routes | Guide |
| --- | --- | --- |
| SSH | `/ssh/<ssh_public_key_name>` | [Verify and import a public key](docs/usage/ssh.md) |
| Mihomo | `/mihomo/install`, `/mihomo/sub`, `/mihomo/restart` | [Install and manage a proxy](docs/usage/mihomo.md) |
| Claude Code | `/claude/install`, `/claude/config` | [Install and apply JSON settings](docs/usage/claude.md) |
| Codex | `/codex/install`, `/codex/config`, `/codex/models_1m` | [Install, configure, and download the model catalog](docs/usage/codex.md) |
| Stash | `/stash/upload0`–`7`, `/stash/download0`–`7`, `/stash/clear` | [Share UTF-8 text](docs/usage/stash.md) |

Deployment publishes tools; it does not install clients, grant SSH access, or sign anyone in. Applying shared Claude/Codex configuration replaces a client file rather than merging it. Stash has no history or expiry; keep all private data out of it.

## Maintain

```sh
git status --short
git pull --ff-only
sudo ./linspace deploy
```

Resolve source edits before pulling and preserve ignored `local/` settings and inputs. Python 3.9/3.10 needs `python3-tomli`. After changing settings with `./linspace configure`, redeploy; clients reapply shared configuration explicitly. Each installation has independent tokens and channel data.

For rotation, rollback, backups, and logs, use [operations](docs/operations.md). To build without deploying:

```sh
./linspace build   # Configured archives in dist/
./linspace check   # Offline checks; no personal configuration required
```

## Project map

| Location | Purpose |
| --- | --- |
| `config/` | Site schema/templates; public Claude and Codex defaults |
| `local/` | Operator configuration and inputs; ignored |
| `src/` | Mihomo and Stash implementations |
| `scripts/` | Configure, build, deploy, verify, check |
| `assets/` | Pinned GeoIP snapshot and manifest |
| `tests/` | Configuration, build, CLI, verification, deployment, protocol tests |
| `packaging/` | Server and Mihomo bundle README templates |
| `dist/` | Generated releases and archives; ignored |

[Documentation index](docs/README.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE) · [GeoIP provenance](assets/README.md)
