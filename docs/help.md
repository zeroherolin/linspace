# Linspace Help

Linux or macOS with Bash and curl. Run as your own account, without `sudo`.

## Claude Code

```sh
# Install and configure (rerun to update)
curl -fsSL https://your-domain.cn/claude/install | bash && mkdir -p ~/.claude
curl -fsSL https://your-domain.cn/claude/config -o ~/.claude/settings.json
export PATH="$HOME/.local/bin:$PATH"  # add to ~/.bashrc or ~/.zshrc

# Relay credentials (skip for account sign-in)
export ANTHROPIC_BASE_URL='https://relay.example' && \
    export ANTHROPIC_AUTH_TOKEN='YOUR_CLAUDE_TOKEN'
```

## Codex

```sh
# Install and configure (rerun to update)
curl -fsSL https://your-domain.cn/codex/install | bash && mkdir -p ~/.codex
curl -fsSL https://your-domain.cn/codex/config -o ~/.codex/config.toml
curl -fsSL https://your-domain.cn/codex/models_1m -o ~/.codex/models-1m.json
export PATH="$HOME/.local/bin:$PATH"

# Relay credentials (or omit -s ... and follow the prompts)
curl -fsSL https://your-domain.cn/codex/auth | bash \
    -s -- -t 'YOUR_CODEX_TOKEN' -u 'https://relay.example/v1'
```

## Uninstall

```sh
# Removes installations, settings and credentials; conversation history is kept
curl -fsSL https://your-domain.cn/claude/uninstall | bash
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```
