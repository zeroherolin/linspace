# Claude Code

Run as the account that will use Claude Code on supported Linux or macOS. You need curl and access to the site and Anthropic's services. See the [official setup requirements](https://code.claude.com/docs/en/setup).

## Install and update

```sh
curl -fsSL https://your-domain.cn/claude/install | bash
claude --version
```

The site redirects to the official `https://claude.ai/install.sh`; it does not mirror or pin it. Follow the installer PATH instructions. Native installs support automatic updates; use `claude update` for an immediate update or `claude doctor` for diagnostics.

## Configure and sign in

`/claude/config` serves the JSON selected by the operator's `claude_settings_file`. The [bundled preset](../../config/claude/settings.json) selects `claude-fable-5-1[1m]`, Chinese responses, `xhigh` effort, tool permissions, plugin and UI preferences. Its built-in sandbox is disabled. Authentication credentials are not included.

Use the [shared configuration procedure](client-config.md) with `client=claude`. It backs up and replaces `settings.json` under `CLAUDE_CONFIG_DIR`, or `~/.claude` by default. Review the file first; replacement does not merge personal preferences. See [configuration directories](https://code.claude.com/docs/en/claude-directory) and [settings precedence](https://code.claude.com/docs/en/settings).

Run `claude` in your project and complete normal authentication. Publishing settings does not sign users in or update existing clients automatically. For connection problems, configure the [Mihomo proxy](mihomo.md#use-and-restart) first. If the site is unavailable, use the official installer URL and obtain the generated configuration from the operator through a trusted transfer.
