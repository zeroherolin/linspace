# Configuration files

The [Claude Code](claude.md) and [Codex](codex.md) guides show direct downloads for a new client. Run them as the client account, without sudo.

## Locations

| Client | Default directory | Custom directory variable |
| --- | --- | --- |
| Claude Code | `~/.claude` | `CLAUDE_CONFIG_DIR` |
| Codex | `~/.codex` | `CODEX_HOME` |

If a custom directory is set, substitute that absolute path in the download commands. The `/codex/auth` script follows `CODEX_HOME` automatically.

| Download | Save as |
| --- | --- |
| `/claude/config` | `settings.json` in the Claude directory |
| `/codex/config` | `config.toml` in the Codex directory |
| `/codex/models_1m` | `models-1m.json` beside `config.toml` |

Keep configuration directories at mode `700` and files at `600`. The catalog path in the Codex preset is relative; no username replacement is needed.

## Existing installations

Downloads **replace whole files**, rather than merging settings. Back up files you have customized before downloading, for example:

```sh
cp -p ~/.claude/settings.json ~/.claude/settings.json.bak
```

```sh
cp -p ~/.codex/config.toml ~/.codex/config.toml.bak
cp -p ~/.codex/models-1m.json ~/.codex/models-1m.json.bak
```

Use an unused backup filename if `.bak` already exists. A failed direct download may leave a partial file: retry successfully or restore your backup before starting the client.

Configuration downloads do not change login credentials. The separate [Codex auth script](codex.md#authenticate) backs up and atomically replaces `auth.json`. Its optional `-u` also updates the selected provider's `base_url`; without `-u`, `config.toml` stays untouched.

Restart the client after changing settings or the catalog. Site updates do not update client files automatically.

## Command lookup

If `claude` or `codex` is not found, run the PATH command printed by the installer. The default is:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Commands use `~/.local/bin` by default; Codex also accepts `CODEX_INSTALL_DIR`. Use the installer’s printed path when customized.

This changes only the current terminal. For future terminals, add that line yourself to `~/.bashrc` (interactive Bash) or `~/.zshrc` (Zsh). Bash login shells read the first existing `~/.bash_profile`, `~/.bash_login` or `~/.profile`; keep it sourcing your Bash configuration. The installer does not modify these files.
