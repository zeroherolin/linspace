# User quick start

Replace `your-domain.cn` with your site's domain. Run commands one at a time and stop if a command fails. Client machines do not need this Git repository.

These examples use the default configuration directories. Downloads replace existing settings; see [configuration files](usage/client-config.md) for backups and custom directories.

## 1. SSH access

Run as the account that should accept SSH logins. Replace `team.pub` with the site's published key filename.

```sh
install -d -m 700 ~/.ssh
curl -fsSL https://your-domain.cn/ssh/team.pub -o ~/.ssh/linspace-site.pub
ssh-keygen -lf ~/.ssh/linspace-site.pub -E sha256
```

Compare the fingerprint with the one supplied by the operator. After it matches, append the key once:

```sh
echo >> ~/.ssh/authorized_keys
cat ~/.ssh/linspace-site.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

This permits incoming SSH login. It does not give this machine a private key for Stash uploads. [SSH guide](usage/ssh.md).

## 2. Mihomo

Run this section as **root on Debian/Ubuntu**, x86_64 or ARM64.

```sh
curl -fsSL https://your-domain.cn/mihomo/install | bash
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s -- 'https://subscription.example/your-path'
```

A local YAML path can replace the subscription URL. Importing a valid subscription starts the proxy. To use it in the current terminal:

```sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
```

After reboot or process exit:

```sh
curl -fsSL https://your-domain.cn/mihomo/restart | bash
```

[Mihomo guide](usage/mihomo.md).

## 3. Claude Code

Run as the account that will use Claude Code.

```sh
curl -fsSL https://your-domain.cn/claude/install | bash
install -d -m 700 ~/.claude
curl -fsSL https://your-domain.cn/claude/config -o ~/.claude/settings.json
chmod 600 ~/.claude/settings.json
```

Review the shared preset before applying it; the bundled preset disables Claude's sandbox. Run `claude` from your project and sign in. Settings do not include credentials. [Claude Code guide](usage/claude.md).

## 4. Codex

Run as the account that will use Codex.

```sh
curl -fsSL https://your-domain.cn/codex/install | bash
install -d -m 700 ~/.codex
curl -fsSL https://your-domain.cn/codex/config -o ~/.codex/config.toml
curl -fsSL https://your-domain.cn/codex/models_1m -o ~/.codex/models-1m.json
chmod 600 ~/.codex/config.toml ~/.codex/models-1m.json
```

The bundled preset uses an OpenAI-compatible relay and `danger-full-access`; review it before applying. Keep the catalog beside `config.toml`.

Save your provider's API token at the hidden prompt:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash
```

To save the token and change the relay URL together:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash -s -- -t 'YOUR_CODEX_TOKEN' -u 'https://relay.example/v1'
```

Without `-u`, the existing URL is unchanged. The option requires the downloaded configuration and Python with a TOML parser; see the [Codex guide](usage/codex.md#authenticate).

Run `codex` from your project. For ChatGPT account sign-in, use `codex login` instead of the token script. [Codex guide](usage/codex.md).

## 5. Stash

Uploads and clear require an authorized private key or agent. Reads are public. Clients need Python 3.9+ and OpenSSH 8.2+ in addition to Bash and curl.

```sh
curl -fsSL https://your-domain.cn/stash/upload | bash -s -- 'file.txt'
curl -fsSL https://your-domain.cn/stash/download -o received.txt
curl -fsSL https://your-domain.cn/stash/clear | bash
```

`upload` and `download` mean channel 0. Use `upload0`–`upload7` and `download0`–`download7` for the eight channels. Each holds one UTF-8 file up to 1 MiB. Clear removes all eight channels.

The client finds a matching key in `ssh-agent` or `~/.ssh`; normally no `-i` or token is needed. [Stash guide](usage/stash.md).

## Server and maintainer guides

[Deploy](../README.md#deploy) · [Deployment details](deployment.md) · [Operations](operations.md) · [Architecture](architecture.md) · [Stash protocol](stash-auth.md) · [Contributing](../CONTRIBUTING.md) · [Testing](testing.md)
