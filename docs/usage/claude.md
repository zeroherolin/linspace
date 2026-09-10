# Claude Code

Run as the account that will use Claude Code on supported Linux or macOS. You need Bash, curl and access to the site and Anthropic's services.

## Install and update

```sh
curl -fsSL https://your-domain.cn/claude/install | bash
claude --version
```

The site redirects to the [official installer](https://code.claude.com/docs/en/setup). Follow its PATH instructions. Use `claude update` to update or `claude doctor` to diagnose an installation.

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
