# Uninstall

These commands stop the selected program and remove its recognized installations, settings, login credentials and caches. **Claude Code and Codex keep only conversation history.** No backup is created.

Run Claude/Codex uninstall as the account using the client. Run Mihomo uninstall as root on Linux.

```sh
curl -fsSL https://your-domain.cn/mihomo/uninstall | bash
```

```sh
curl -fsSL https://your-domain.cn/claude/uninstall | bash
```

```sh
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```

Preview a command by adding `-s -- --dry-run` after `bash`. An executable outside the normal locations or PATH can be included with `-s -- --bin '/absolute/path/to/codex'` (use the relevant program name).

## Scope

| Program | Recognized sources | Retained data |
| --- | --- | --- |
| Claude Code | linspace, official native, legacy local npm, global npm, pnpm, Yarn, Bun, Homebrew, Linux packages and identified binaries in PATH | `~/.claude/projects/` and `history.jsonl` |
| Codex | linspace, official standalone, global npm, pnpm, Yarn, Bun, Homebrew, Linux packages and identified binaries in PATH | `~/.codex/sessions/`, `archived_sessions/`, `history.jsonl`, `session_index.jsonl` and session state databases |
| Mihomo | linspace background process, official manual layout, systemd, dedicated Supervisor configuration, Homebrew and Linux packages | None; subscriptions, GeoIP, settings and logs are removed |

Custom `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `CODEX_INSTALL_DIR` and XDG paths are honored alongside default locations. Use the same variables used during installation. History stays in place for a later reinstall.

Package-managed installations are removed with their package manager; shared package caches are left to that manager. System packages need administrator access; a regular client account is told what must be removed before retrying. Unknown layouts, shared launchers and shared service configurations stop with an actionable error instead of reporting a complete uninstall.

The scope is the current account and identified system CLI installations. Other accounts, project directories, IDE extensions, desktop application bundles and shared Node/Python installations are not removed. Close IDE/desktop integrations that share the client configuration; they can recreate it. Shell startup files are never edited. Tokens exported by the parent shell must be cleared there separately.

After removing Mihomo, clear proxy variables in the current terminal:

```sh
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
```

Open a new terminal after uninstalling to clear cached command locations. Reinstalling uses the normal install/configuration commands; preserved history remains available.

[Claude's official uninstall guide](https://code.claude.com/docs/en/installation#uninstall-claude-code) · [Codex installation locations](https://learn.chatgpt.com/docs/config-file/environment-variables)
