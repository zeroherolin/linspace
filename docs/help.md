# Linspace Help

Linux or macOS with Bash and curl. Run as your own account, without `sudo`.

## Claude Code

```sh
# Install and configure (rerun to update)
curl -fsSL https://your-domain.cn/claude/install | bash && install -d -m 700 ~/.claude
curl -fsSL https://your-domain.cn/claude/config -o ~/.claude/settings.json && chmod 600 ~/.claude/settings.json
export PATH="$HOME/.local/bin:$PATH"  # add to ~/.bashrc or ~/.zshrc

# Relay credentials (skip for account sign-in)
export ANTHROPIC_BASE_URL='https://relay.example' && \
    export ANTHROPIC_AUTH_TOKEN='YOUR_CLAUDE_TOKEN'

# Start in your project directory
cd /path/to/project && claude
```

## Codex

```sh
# Install and configure (rerun to update)
curl -fsSL https://your-domain.cn/codex/install | bash && install -d -m 700 ~/.codex
curl -fsSL https://your-domain.cn/codex/config -o ~/.codex/config.toml
curl -fsSL https://your-domain.cn/codex/models_1m -o ~/.codex/models-1m.json
chmod 600 ~/.codex/config.toml ~/.codex/models-1m.json
export PATH="$HOME/.local/bin:$PATH"

# Relay credentials: prompts for base_url, then reads the token hidden
curl -fsSL https://your-domain.cn/codex/auth | bash
# Or pass both explicitly (visible in shell history and the process list):
# curl -fsSL https://your-domain.cn/codex/auth | bash \
#     -s -- -t 'YOUR_CODEX_TOKEN' -u 'https://relay.example/v1'

# Start in your project directory
cd /path/to/project && codex
```

## Uninstall

```sh
# Removes installations, settings, credentials, caches and installed plugins.
# Keeps conversation history and your own files: Claude Code projects/, CLAUDE.md,
# commands/, agents/, skills/, plans/, hooks/, rules/; Codex sessions/, AGENTS.md,
# prompts/, skills/, memories/, rules/, hooks/
curl -fsSL https://your-domain.cn/claude/uninstall | bash
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```
