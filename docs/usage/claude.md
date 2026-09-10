# Claude Code

Run as the account that will use Claude Code on supported Linux or macOS. You need Bash, curl, tar, gzip and a SHA256 tool. Model access still requires Anthropic or your configured provider.

## Install and update

```sh
curl -fsSL https://your-domain.cn/claude/install | bash
export PATH="$HOME/.local/bin:$PATH"
claude --version
```

The script reuses a working same-version or newer installation. Otherwise it installs a reviewed native package, with verified download fallback. It never edits shell startup files or retains launcher backups. Rerun to update a linspace installation; update an older external installation with its original installer or package manager.

## Configure

These commands replace the current settings. For an existing installation or a custom directory, read [configuration files](client-config.md) first.

```sh
install -d -m 700 ~/.claude
curl -fsSL https://your-domain.cn/claude/config -o ~/.claude/settings.json
chmod 600 ~/.claude/settings.json
```

Review the [bundled preset](../../config/claude/settings.json) before applying it. It selects `claude-fable-5-1[1m]`, Chinese responses and `xhigh` effort, and disables Claude's built-in sandbox. The operator may publish different settings.

## Sign in and use

From your project directory:

```sh
claude
```

Complete authentication when prompted. Shared settings contain no credentials. If a proxy is needed, [enable it in the current terminal](mihomo.md#use-and-restart) first.

Restart Claude after replacing settings. [Official settings reference](https://code.claude.com/docs/en/settings).

## Uninstall

```sh
curl -fsSL https://your-domain.cn/claude/uninstall | bash
```

Stops Claude Code and removes recognized CLI installations, settings and credentials, keeping only conversation history. [Scope and preview](uninstall.md).
