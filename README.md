# linspace

An HTTPS toolbox for SSH keys, Mihomo, Claude Code, Codex and eight public text channels.

**Use an existing site:** open its `/help` page or read the [user guide](docs/usage.md). **Host your own:** follow the steps below.

## Deploy

Use Debian 12+ or Ubuntu 22.04+ with systemd and root/sudo access. Run project commands from the Git checkout; omit `sudo` when already root.

### 1. Prepare your domain

Use an already-resolved, ICP-filed domain with its approved website name and complete filing number.

- Point its A record to the server; add AAAA only if public IPv6 works.
- Allow TCP **80/443** in the cloud security group and host firewall. Caddy also advertises HTTP/3; allow UDP **443** as well, or clients fall back to TCP after a short delay. Keep SSH available.
- Free ports 80/443, or use an existing Caddy 2.10+ installation.
- Allow outbound access to package repositories and certificate authorities.

Check DNS for the hostname you want to serve. The site has one canonical hostname; if the filing also names another form, such as `www.your-domain.cn`, point that record at the same server and list it under `alias_domains` so it redirects here. The project creates no DNS records:

```sh
getent ahosts your-domain.cn
getent ahosts www.your-domain.cn   # only when you configure an alias
```

### 2. Install prerequisites and clone

```sh
sudo apt-get update
sudo apt-get install -y git python3 curl ca-certificates openssh-client
cd ~
git clone https://github.com/zeroherolin/linspace.git
cd linspace
```

Python 3.9+ is required; the TOML parser is bundled. No Node.js, Docker or database is needed.

### 3. Configure

```sh
./linspace configure
```

The wizard saves `local/site.json`, which Git ignores. Enter keeps the current value.

| Setting | What to enter |
| --- | --- |
| `domain` | Your canonical hostname, such as `tools.your-domain.cn`; no scheme, port or path |
| `alias_domains` | Hostnames that permanently redirect to `domain`, such as `www.your-domain.cn`; up to 8, `-` or `[]` for none |
| `site_name` | Approved website name |
| `icp_number` | Complete issued filing number, including its site suffix |
| `ssh_public_key_file` | Public `.pub` file; `-` disables publishing |
| `ssh_public_key_name` | Published filename, such as `team.pub`; default `key.pub` |
| `claude_settings_file` | Default `config/claude/settings.json` |
| `codex_config_file` | Default `config/codex/config.toml` |
| `stash_public_key_files` | `auto` (JSON `null`): reuse the SSH key; JSON path array: separate keys; `[]`: disable writes |

The wizard copies the SSH key into `local/keys/` and publishes it at `/ssh/<ssh_public_key_name>`. Relative paths resolve from the checkout; `~/` is expanded when configuring.

Client settings are public. Known credential fields are rejected, but review the presets: Claude disables its sandbox, and Codex uses a relay with `danger-full-access`. Keep custom input files in `local/`. [Configuration template](config/site.example.json).

### 4. Preview and deploy

```sh
./linspace urls
./linspace deploy --dry-run
sudo ./linspace deploy
```

Deployment installs Caddy when needed, obtains HTTPS certificates, backs up managed state and activates the site. Existing channel data is preserved. [Existing Caddy and recovery](docs/operations.md).

### 5. Verify

```sh
./linspace verify
sudo systemctl is-active caddy stashd.socket
```

Verification checks public HTTPS without changing channel data. If it fails, use [diagnostics](docs/operations.md#diagnostics). Testing Stash uploads needs an authorized SSH key; deployment installs no private key on clients.

## Use

The [user guide](docs/usage.md) covers SSH key import, Mihomo, Claude Code, Codex, Stash and uninstall. The site's `/help` page is built from [docs/help.md](docs/help.md). Installers reuse compatible existing clients and fall back to verified downloads when upstream access fails. Uninstall keeps Claude Code and Codex conversation history and user-authored files. Stash reads are public; writes use SSH signatures.

## Update

```sh
git status --short
git pull --ff-only
sudo ./linspace deploy
```

Resolve local source edits before pulling; ignored `local/` files are kept. After reconfiguring, redeploy; clients download updated settings themselves.

[Operations](docs/operations.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
