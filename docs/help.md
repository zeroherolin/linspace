# Linspace Help

Linux or macOS with Bash and curl. Run the commands as your own account and stop if one fails. Configuration downloads replace existing files.

## tmux

Keeps terminal sessions alive across disconnects. Requires tmux 3.2+: Linux installs it with the package manager and may ask for sudo; macOS needs Homebrew.

```sh
# Install and configure
curl -fsSL https://your-domain.cn/tmux/install | bash
curl -fsSL https://your-domain.cn/tmux/config -o ~/.tmux.conf
chmod 600 ~/.tmux.conf

# Start or reconnect
tmux new-session -A -s work
```

Press `Ctrl-b`, then `d` to detach; the session keeps running. After editing `~/.tmux.conf`, apply it with `tmux source-file ~/.tmux.conf`.

## Claude Code

Install the client, apply the shared settings, then start in your project. Use the relay settings only for API access.

```sh
# Install and configure
curl -fsSL https://your-domain.cn/claude/install | bash && install -d -m 700 ~/.claude
curl -fsSL https://your-domain.cn/claude/config -o ~/.claude/settings.json
chmod 600 ~/.claude/settings.json
export PATH="$HOME/.local/bin:$PATH"

# Optional: relay credentials
# export ANTHROPIC_BASE_URL='https://relay.example'
# export ANTHROPIC_AUTH_TOKEN='YOUR_CLAUDE_TOKEN'

# Start
cd /path/to/project && claude
```

## Codex

Keep the configuration and model catalog together. The optional auth command asks for the relay URL, then reads the token without echo.

```sh
# Install and configure
curl -fsSL https://your-domain.cn/codex/install | bash && install -d -m 700 ~/.codex
curl -fsSL https://your-domain.cn/codex/config -o ~/.codex/config.toml
curl -fsSL https://your-domain.cn/codex/models_1m -o ~/.codex/models-1m.json
chmod 600 ~/.codex/config.toml ~/.codex/models-1m.json
export PATH="$HOME/.local/bin:$PATH"

# Optional: relay credentials
# curl -fsSL https://your-domain.cn/codex/auth | bash

# Start
cd /path/to/project && codex
```

For future terminals, add the PATH export to `~/.bashrc` or `~/.zshrc`. Rerun the install commands to update; download the settings again when the operator changes them.

## Uninstall

Run only the command for the tool you want to remove. **Only Claude Code and Codex session records are kept.** Settings, credentials, plugins, skills and other client data are deleted without backups; removing tmux also deletes `~/.tmux.conf`.

```sh
curl -fsSL https://your-domain.cn/tmux/uninstall | bash
curl -fsSL https://your-domain.cn/claude/uninstall | bash
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```

Add `-s -- --dry-run` after `bash` to preview. Close all tmux sessions before removing tmux. Project files and shell startup files are untouched.
