# linspace

An HTTPS toolbox for SSH keys, Mihomo, Claude Code, Codex and eight public text channels.

**Use an existing site:** [User quick start](docs/README.md). **Host your own:** follow the steps below.

## Deploy

Use Debian 12+ or Ubuntu 22.04+ with systemd and root/sudo access. Run project commands from the Git checkout. Omit `sudo` when already root.

### 1. Prepare your domain

Use an already-resolved, ICP-filed domain with its approved website name and complete filing number.

- Point its A record to the server; add AAAA only if public IPv6 works.
- Allow TCP **80/443** in the cloud security group and host firewall. Keep SSH available.
- Free ports 80/443, or use an existing Caddy 2.10+ installation.
- Allow outbound access to package repositories and certificate authorities.

Check DNS:

```sh
getent ahosts your-domain.cn
```

Use the exact hostname you want to serve. The project does not create DNS records or add `www`.

### 2. Install prerequisites and clone

```sh
sudo apt-get update
sudo apt-get install -y git python3 curl ca-certificates openssh-client
cd ~
git clone https://github.com/zeroherolin/linspace.git
cd linspace
```

Python 3.9+ is required; the TOML parser is bundled. The server needs no Node.js, Docker or database.

### 3. Configure

```sh
./linspace configure
```

The wizard saves `local/site.json`, which Git ignores. Enter keeps the current value.

| Setting | What to enter |
| --- | --- |
| `domain` | Your hostname, such as `tools.your-domain.cn`; no scheme, port or path |
| `site_name` | Approved website name |
| `icp_number` | Complete issued filing number, including its site suffix |
| `ssh_public_key_file` | Public `.pub` file; `-` in the wizard disables publishing |
| `ssh_public_key_name` | Published filename, such as `team.pub`; default `key.pub` |
| `claude_settings_file` | Default: `config/claude/settings.json` |
| `codex_config_file` | Default: `config/codex/config.toml` |
| `stash_public_key_files` | `auto` in the wizard / `null` in JSON: reuse the SSH key; JSON path array: separate keys; `[]`: disable writes |

The SSH key above is published at `/ssh/team.pub` when that filename is selected. The wizard copies it into `local/keys/`. Relative input paths resolve from the checkout; `~/` paths are expanded when configuring.

Client settings are public. Known credential fields are rejected, but still review the presets: Claude disables its sandbox, and Codex uses a relay with `danger-full-access`. Keep custom input files in `local/`. See the [configuration template](config/site.example.json).

### 4. Preview and deploy

```sh
./linspace urls
./linspace deploy --dry-run
sudo ./linspace deploy
```

Deployment installs Caddy when needed, obtains HTTPS certificates, backs up managed state and activates the site. Existing channel data is preserved. [Existing Caddy and recovery](docs/deployment.md).

### 5. Verify

```sh
./linspace verify
sudo systemctl is-active caddy stashd.socket
```

Verification checks public HTTPS without changing channel data. If it fails, use [diagnostics](docs/operations.md#diagnostics). An authorized SSH key is required to test Stash uploads; deployment does not install a private key on clients.

## Use

| Feature | Guide |
| --- | --- |
| SSH | [Verify and authorize a public key](docs/usage/ssh.md) |
| Mihomo | [Install, import a subscription and use the proxy](docs/usage/mihomo.md) |
| Claude Code | [Install, configure and sign in](docs/usage/claude.md) |
| Codex | [Install, configure and authenticate](docs/usage/codex.md) |
| Stash | [Upload, read and clear text](docs/usage/stash.md) |

Linux installers automatically use verified fallback downloads when upstream access fails.

Installers reuse compatible existing clients and keep no permanent installation backups. Each client has an [uninstall endpoint](docs/usage/uninstall.md); Claude/Codex retain conversation history only.

The [quick start](docs/README.md) puts the common commands on one page. Stash reads are public; writes use SSH signatures and normally need no `-i` or token.

## Update

```sh
git status --short
git pull --ff-only
sudo ./linspace deploy
```

Resolve local source edits before pulling. Keep ignored `local/` files. After reconfiguring, redeploy; clients must download updated settings themselves.

[Operations](docs/operations.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [Testing](docs/testing.md) · [MIT license](LICENSE) · [Bundled dependencies](vendor/README.md)
