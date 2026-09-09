# Install Claude Code and apply shared settings

Ask the site operator for the base URL and replace `your-domain.cn` in the examples. The operator can run `./linspace urls` in the repository checkout; the client does not need a checkout.

Run these commands in Bash as the account that will use Claude Code, on a supported Linux or macOS system. The account needs curl and access to the site and Anthropic's installation/login endpoints. Follow the [official setup requirements](https://code.claude.com/docs/en/setup) for supported platforms and dependencies.

## Install and update

`/claude/install` returns a 302 redirect to `https://claude.ai/install.sh`; the site does not mirror or pin that installer. `curl -L` follows the redirect:

```sh
curl -fsSL https://your-domain.cn/claude/install | bash
```

To inspect the script first, replace `| bash` with `| less`. Follow its PATH instructions, then check the installed command:

```sh
claude --version
```

The native launcher is at `~/.local/bin/claude`; add `~/.local/bin` to PATH if needed. Native installations normally update in the background. For an immediate update, run `claude update`; `claude doctor` reports installation/update issues. See [official update behavior](https://code.claude.com/docs/en/setup#update-claude-code).

When direct access is unavailable, start the local [mihomo proxy](mihomo.md) and export `http_proxy` and `https_proxy` in the shell first.

## Apply the shared configuration

The site publishes the JSON selected by the operator's `claude_settings_file`. The repository's [default input](../../config/claude/settings.json) contains `{}`, but a deployed site may use a different file. The build serializes that input before publishing it.

**Applying the downloaded file replaces the entire user-level `settings.json`; it does not merge preferences.** An empty file removes the overrides that were previously in that file. Other settings scopes and their precedence still apply, as described in the [official settings documentation](https://code.claude.com/docs/en/settings). Review or merge the shared settings if you want to retain personal changes.

This procedure downloads to a temporary file, saves an existing settings file to a unique backup, and then replaces it:

```bash
(
    set -euo pipefail
    install -d -m 700 ~/.claude
    settings_file=$(mktemp ~/.claude/.settings.XXXXXX)
    trap 'rm -f "$settings_file"' EXIT
    curl -q -fsSL --proto '=https' --proto-redir '=https' \
        https://your-domain.cn/claude/config -o "$settings_file"
    if [[ -f ~/.claude/settings.json ]]; then
        backup_file=$(mktemp ~/.claude/settings.json.backup.XXXXXX)
        cp -p ~/.claude/settings.json "$backup_file"
        chmod 600 "$backup_file"
        printf 'Previous settings: %s\n' "$backup_file"
    fi
    chmod 600 "$settings_file"
    mv -f "$settings_file" ~/.claude/settings.json
)
```

For an integrity comparison, ask the operator for the digest of the active `/srv/linspace/current/claude/config` or the `site/claude/config` entry in that release's `SHA256SUMS`. Do not compare with an arbitrarily formatted input JSON file or a newer, undeployed build. On Linux use `sha256sum ~/.claude/settings.json`; on macOS use `shasum -a 256 ~/.claude/settings.json`.

Publishing or building settings does not apply them to any client. Existing clients must deliberately reapply an update. The shared file must contain no credentials; the first interactive run of `claude` still uses its normal authentication flow.

## When the site is unavailable

Install directly from the official destination:

```sh
curl -fsSL https://claude.ai/install.sh | bash
```

Obtain the selected generated `site/claude/config` from the operator through a trusted transfer, back up your current settings, and install it as `~/.claude/settings.json` with mode 0600. The website itself is not required for this fallback.
