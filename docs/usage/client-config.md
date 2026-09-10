# Apply shared client configuration

This is the common procedure for [Claude Code](claude.md) and [Codex](codex.md). Run in Bash as the client account. Set your domain and choose `client=claude` or `client=codex`.

**This replaces one complete configuration file.** Review the shared file first and merge manually if you need to retain personal settings. Presets define model, provider and access settings; replacement removes preferences absent from the downloaded file. Builds validate syntax and catalog consistency; settings must also suit the installed client version.

```bash
(
    set -euo pipefail
    client=codex
    base_url=https://your-domain.cn
    case "$client" in
        claude) config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"; config_name=settings.json ;;
        codex) config_dir="${CODEX_HOME:-$HOME/.codex}"; config_name=config.toml ;;
        *) echo 'Choose claude or codex' >&2; exit 1 ;;
    esac
    install -d -m 700 "$config_dir"
    downloaded=$(mktemp "$config_dir/.config.XXXXXX")
    trap 'rm -f "$downloaded"' EXIT
    curl -q -fsSL --proto '=https' --proto-redir '=https' \
        --connect-timeout 10 --max-time 60 \
        "$base_url/$client/config" -o "$downloaded"
    if [[ -f "$config_dir/$config_name" ]]; then
        backup=$(mktemp "$config_dir/$config_name.backup.XXXXXX")
        cp -p "$config_dir/$config_name" "$backup"
        chmod 600 "$backup"
        printf 'Previous configuration: %s\n' "$backup"
    fi
    chmod 600 "$downloaded"
    mv -f "$downloaded" "$config_dir/$config_name"
)
```

The destination follows `CLAUDE_CONFIG_DIR` or `CODEX_HOME` when set, otherwise the current user's `~/.claude` or `~/.codex`. Use an absolute directory for either environment variable. Run as that user, without sudo.

For Codex, also [download the model catalog beside the configuration](codex.md#download-the-model-catalog) before starting the client; this shared procedure replaces only `config.toml`.

A failed download leaves the existing file untouched. The unique backup remains beside it; restore that file to undo replacement. Authentication files are separate and remain untouched.

For an integrity comparison, ask the operator for the SHA256 of the **active generated** `/srv/linspace/current/claude/config` or `/srv/linspace/current/codex/config`; the catalog is `/srv/linspace/current/codex/models_1m`. Use `sha256sum` on Linux or `shasum -a 256` on macOS. Claude's input JSON may be formatted differently before building; compare the published bytes. Clients must deliberately repeat the procedure after an operator update.
