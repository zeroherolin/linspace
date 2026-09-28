# User guide

Commands for using a linspace site. Replace `your-domain.cn` with the site domain and `page.your-domain.cn` with its page host. Run them as the account that will use the tool; Mihomo needs root, and Linux tmux installation may ask for sudo. Stop when a command fails. The site's `/help` page shows the tmux, Claude Code and Codex commands in short form; `/help2` covers every section.

## Requirements

| Feature | Platform | Tools |
| --- | --- | --- |
| SSH, Stash and page writes | Linux or macOS | OpenSSH 8.2+ |
| Mihomo | Debian/Ubuntu x86_64/ARM64, root | Bash, curl, tar, gzip, diff, `sha256sum` or `shasum` |
| tmux | Linux or macOS | apt/dnf/yum/pacman/apk, or Homebrew on macOS |
| Claude Code, Codex | Linux x86_64/ARM64 (glibc), macOS Intel/Apple Silicon | same as Mihomo |

Download-based installers use official sources first, then verified fallback downloads. The tmux installer uses the host package manager. Installers never edit shell startup files. Missing Python for Codex auth or uninstall is downloaded as a verified runtime.

## SSH

Run as the account that should accept SSH logins. Ask the operator for the published filename (`team.pub` below) and the expected SHA-256 fingerprint.

```sh
install -d -m 700 ~/.ssh
curl -fsSL https://your-domain.cn/ssh/team.pub -o ~/.ssh/linspace-site.pub
ssh-keygen -lf ~/.ssh/linspace-site.pub -E sha256
```

Stop if the fingerprint differs. Then append the key once:

```sh
echo >> ~/.ssh/authorized_keys
cat ~/.ssh/linspace-site.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Existing keys are preserved. Connect from the machine holding the matching private key with `ssh user@server`, adding `-i /path/to/private_key` for a nonstandard key path. Importing a public key permits incoming login; it does not let the target machine sign [Stash](#stash) uploads.

## Mihomo

Run as root on the client that needs a proxy.

```sh
curl -fsSL https://your-domain.cn/mihomo/install | bash
curl -fsSL https://your-domain.cn/mihomo/sub | bash
```

Install fetches the pinned Mihomo version, GeoIP and Python when needed; nothing starts until a subscription is imported. The import script asks for the subscription address on the terminal without echoing it, so the address stays out of shell history and the process list; for scripts, pass it as an argument: `bash -s -- 'https://subscription.example/your-path'`. The subscription may also be a local file path. It must be a Clash/Mihomo YAML with a nonempty `proxies` array; provider-only subscriptions and nodes that disable TLS verification are rejected. Import selects the first working node and starts the proxy; a failed import keeps the previous state. Keep subscriptions private.

Use the proxy in the terminal running your client:

```sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
curl -fsSI --proxy http://127.0.0.1:7890 --noproxy '' https://www.google.com
```

The listener is local. Rules send China IPs directly and other traffic through the selected node. Restart after a reboot or process exit, or when the selected node stops working; there is no autostart or watchdog:

```sh
curl -fsSL https://your-domain.cn/mihomo/restart | bash
```

Restart starts the process again and checks the selected node. While that node passes the HTTPS check the selection is kept; otherwise the imported subscription is searched the way import does, in subscription order, and the first node that passes is selected. If no node passes, the process keeps running with its previous selection and the command fails; import a new subscription or retry later. Nothing is downloaded and the subscription files are not changed.

Diagnose with the process status and log:

```sh
/usr/local/lib/linspace-mihomo/python /usr/local/lib/linspace-mihomo/process.py status
tail -n 50 /var/log/mihomo/mihomo.log
```

Configuration is `/etc/mihomo/config.yaml`; nodes and GeoIP are under `/var/lib/mihomo/`. TUN, built-in DNS, sniffing and automatic updates are disabled. If site downloads are unavailable, use the [Mihomo bundle](mihomo-bundle.md) from the operator.

## tmux

Install tmux through the host package manager and download the shared configuration:

```sh
curl -fsSL https://your-domain.cn/tmux/install | bash
curl -fsSL https://your-domain.cn/tmux/config -o ~/.tmux.conf
chmod 600 ~/.tmux.conf
tmux new-session -A -s work
```

Linux uses the first available `apt-get`, `dnf`, `yum`, `pacman` or `apk` and may ask for sudo; macOS uses Homebrew. An existing tmux 3.2 or newer is reused; older versions are rejected because the shared configuration needs 3.2. The installer does not edit shell startup files or write `~/.tmux.conf`; the configuration is a separate explicit download that replaces the file.

After editing `~/.tmux.conf`, apply it to the running server with `tmux source-file ~/.tmux.conf`; new servers read the file when they start. `Ctrl-b` then `d` detaches, and the same `new-session -A` command reconnects.

## Claude Code

```sh
curl -fsSL https://your-domain.cn/claude/install | bash
export PATH="$HOME/.local/bin:$PATH"
install -d -m 700 ~/.claude
curl -fsSL https://your-domain.cn/claude/config -o ~/.claude/settings.json
chmod 600 ~/.claude/settings.json
```

The installer reuses a working same-version or newer client; otherwise it installs the reviewed native package. Rerun to update. An installation from another source is updated with its own installer or package manager.

The download replaces `settings.json`. The [bundled preset](../config/claude/settings.json) selects `claude-fable-5-1[1m]`, Chinese responses and `xhigh` effort, and disables the sandbox; the operator may publish a different one. It contains no credentials.

Start `claude` in your project directory and follow the sign-in prompts. For a relay, set its address and token in the current terminal first:

```sh
export ANTHROPIC_BASE_URL="https://relay.example"
export ANTHROPIC_AUTH_TOKEN="YOUR_CLAUDE_TOKEN"
claude
```

Unset both variables before switching back to account sign-in. Restart after changing settings. [Official settings reference](https://code.claude.com/docs/en/settings).

## Codex

```sh
curl -fsSL https://your-domain.cn/codex/install | bash
export PATH="$HOME/.local/bin:$PATH"
install -d -m 700 ~/.codex
curl -fsSL https://your-domain.cn/codex/config -o ~/.codex/config.toml
curl -fsSL https://your-domain.cn/codex/models_1m -o ~/.codex/models-1m.json
chmod 600 ~/.codex/config.toml ~/.codex/models-1m.json
```

Install and update behave as for Claude Code. The downloads replace `config.toml` and the model catalog; keep both in the same directory. The [bundled preset](../config/codex/config.toml) selects `gpt-6-astra`, `xhigh` reasoning and a 1M context budget through the relay `https://us.api.openai-next.com/v1`, with `danger-full-access` and `on-request` / `auto_review` approvals. The provider must support the selected model and context size.

Save the provider token:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash
```

The script asks for `base_url` visibly (Enter keeps the current value) and then reads the token hidden. A nonempty URL replaces `base_url` for the provider selected in `config.toml`, which must already be downloaded. For unattended use, pass both values; note that command-line arguments are visible in shell history and the process list, so prefer the prompts on shared machines:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash -s -- -t 'YOUR_CODEX_TOKEN' -u 'https://relay.example/v1'
```

`-t` disables all prompts; without `-u`, `config.toml` is untouched. The URL must be an absolute HTTP(S) address without userinfo, whitespace or a fragment; invalid input changes nothing. Credentials are written to `auth.json` with mode `600` and are not sent to the site or the provider. For ChatGPT account sign-in, use `codex login` instead.

Start `codex` in your project directory; `codex login status` shows whether credentials are saved. Restart after changing settings or the catalog.

## Stash

Eight public text channels, `0`–`7`. Each holds one UTF-8 file up to 1 MiB without NUL bytes; upload replaces the previous file. Reads are public with no history or expiry — keep secrets out. Writes need a private key whose public key the operator has authorized.

```sh
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- 'file.txt'
curl -fsSL https://your-domain.cn/stash/download7 -o received.txt
curl -fsSL https://your-domain.cn/stash/clear | bash
```

`upload` and `download` without a digit mean channel 0. A missing channel returns 404. Clear removes all eight channels; to empty one channel, upload an empty file.

The client tries `ssh-agent`, then `~/.ssh/id_*` pairs, then other `.pub` files with a private key beside them. Use `ssh-add` for encrypted keys, `-i /path/to/private_key` for a one-off key, or `export STASH_IDENTITY=/path/to/private_key` for a persistent one. A public key in `authorized_keys` cannot sign uploads; on a remote machine, authorize that machine's own key or forward an agent.

| Result | Meaning |
| --- | --- |
| No authorized identity | Load the key into the agent or ask the operator to authorize it |
| Writes disabled | The site has no authorized keys |
| 401 | Signature invalid, expired or already used; the client retries once with a fresh challenge, then download the current script and retry |
| 408 | The upload did not finish within 60 seconds; check the connection and retry |
| 411 / 413 / 415 | Missing length, over 1 MiB, or not UTF-8 text without NUL bytes; use the current script |
| 429 / 503 | Retry later; the operator should check service logs |

Successful writes return 204. [Protocol details](architecture.md#stash-authentication).

## Pages

Sites with a page host (`page.your-domain.cn` below) publish single HTML files as web pages. A page's name — up to 48 lowercase letters, digits, hyphens or underscores, starting with a letter or digit — is part of its addresses. Publishing uses the Stash keys and client options above.

```sh
curl -fsSL https://page.your-domain.cn/report/upload | bash -s -- 'report.html'
curl -fsSL https://page.your-domain.cn/report/delete | bash
```

The page opens at `https://page.your-domain.cn/report`; uploading again replaces it. Pages are public with no history or expiry, are not indexed and cannot be framed by other sites.

- Files are UTF-8 up to 4 MiB. Inline images, styles and scripts, or load them from `https://` addresses; relative files such as `./chart.png` are not published.
- The site's filing number follows the page content; a page that never scrolls, such as a full-screen app, may hide it.
- Pages run on the page host, apart from the main site, so browser storage works; all pages share that storage.
- A site holds up to 64 pages and has no public list; delete unused ones.

| Result | Meaning |
| --- | --- |
| Invalid page name | The name in the address breaks the rule above; for example, use `beijing_plan`, not `Beijing Plan` |
| No valid page name | The script was not downloaded from `https://page.your-domain.cn/NAME/upload` |
| 404 on upload | The site does not publish pages |
| 404 on delete | No page has this name |
| 413 | The file exceeds 4 MiB |
| 507 | The site already holds 64 pages; delete one first |

Other results match the Stash table above.

## Custom directories and PATH

| Client | Default directory | Override |
| --- | --- | --- |
| Claude Code | `~/.claude` | `CLAUDE_CONFIG_DIR` |
| Codex | `~/.codex` | `CODEX_HOME`; launcher directory `CODEX_INSTALL_DIR` |

When an override is set, download settings into that directory; the Codex auth script follows `CODEX_HOME` automatically. Configuration downloads replace whole files and leave saved credentials alone; site updates do not refresh client files.

Launchers live in `~/.local/bin`. The installer prints the `export PATH` command for the current terminal; add it to `~/.bashrc`, `~/.zshrc` or your login file for new terminals.

## Uninstall

```sh
curl -fsSL https://your-domain.cn/mihomo/uninstall | bash
curl -fsSL https://your-domain.cn/tmux/uninstall | bash
curl -fsSL https://your-domain.cn/claude/uninstall | bash
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```

Run the Mihomo command as root. Add `-s -- --dry-run` after `bash` to preview; the Mihomo, Claude Code and Codex commands also accept `-s -- --bin /absolute/path` to include an executable outside PATH.

Each command stops the program and removes recognized installations, settings, credentials, caches and installed plugins without backups. **Only session records are kept. Claude Code keeps `~/.claude/projects/` and `history.jsonl`; Codex keeps `sessions/`, `archived_sessions/`, `history.jsonl`, `session_index.jsonl` and session state databases.** User-authored settings, prompts, skills, hooks, rules and other extensions are removed. `~/.claude.json` (per-project trust and MCP settings) is removed. Mihomo retains nothing. The tmux command refuses to run while a tmux server is running, removes the package with its package manager and deletes `~/.tmux.conf`, plugins, sockets and caches.

Recognized sources: linspace, official native or standalone packages, global npm/pnpm/Yarn/Bun, Homebrew, Linux packages and identified binaries in PATH; for Mihomo also systemd, Supervisor and the official manual layout. Package-managed installations are removed with their package manager; system packages need administrator access. Unknown layouts and shared launchers or services stop with an actionable error. Other accounts, IDE extensions, desktop bundles and shared runtimes are never removed. Startup files are never edited; exported tokens must be unset in the parent shell. After removing Mihomo, run `unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY`.

Open a new terminal afterward. Reinstalling uses the normal commands; retained session records remain available.
