# Codex

Run as the account that will use Codex on supported Linux or macOS. You need curl and access to the site and OpenAI's services.

## Install and update

```sh
curl -fsSL https://your-domain.cn/codex/install | sh
codex --version
```

The site returns a 302 to `https://chatgpt.com/codex/install.sh`, the [official standalone installer](https://learn.chatgpt.com/docs/codex/cli). Follow its PATH instructions. Rerun the same command to update; the site does not mirror or pin the installer.

## Configure and sign in

`/codex/config` serves the UTF-8 TOML selected by the operator's `codex_config_file`, preserving formatting and comments. The [bundled preset](../../config/codex/config.toml) selects `gpt-6-astra`, `xhigh` reasoning, a 1,000,000-token context window, live search and a detailed status line. It uses `openai_next` at `https://us.api.openai-next.com/v1`, `on-request` approvals, `auto_review`, and `danger-full-access`. Review these settings and provider before applying.

The companion [model catalog](../../config/codex/models-1m.json) is published at `/codex/models_1m`. Its model-specific instructions and capabilities come from the [recorded official CLI version](../../config/codex/catalog-source.json); three window overrides set a 1M client budget for both models. Keep it beside the TOML file. Credentials, project trust and UI history are not included. [Catalog policy and maintenance](../../config/codex/README.md).

Use the [shared configuration procedure](client-config.md) with `client=codex`. It backs up and replaces `config.toml` under your existing `CODEX_HOME`, or `~/.codex` by default. It does not merge settings. Other configuration layers and managed policies can still apply; see [official configuration basics](https://learn.chatgpt.com/docs/config-file/config-basic).

## Download the model catalog

```bash
(
    set -euo pipefail
    config_dir="${CODEX_HOME:-$HOME/.codex}"
    install -d -m 700 "$config_dir"
    models_file=$(mktemp "$config_dir/.models-1m.XXXXXX")
    trap 'rm -f "$models_file"' EXIT
    curl -q -fsSL --proto '=https' --proto-redir '=https' \
        https://your-domain.cn/codex/models_1m -o "$models_file"
    chmod 600 "$models_file"
    mv -f "$models_file" "$config_dir/models-1m.json"
    printf 'Catalog path: %s/models-1m.json\n' "$(cd "$config_dir" && pwd)"
)
```

Keep the preset’s `model_catalog_json = "models-1m.json"`. Codex resolves this filename relative to the directory containing `config.toml`, not the shell’s working directory. Download both files into the same `CODEX_HOME` directory (default `~/.codex`); no username or absolute-path replacement is needed. The [official sample](https://learn.chatgpt.com/docs/config-file/config-sample) also supports relative catalog paths.

Codex loads this catalog at startup, so restart the client after updating it. A catalog controls client-side model metadata; it cannot increase a provider's actual context limit. See [official model-catalog configuration](https://learn.chatgpt.com/docs/config-file/config-reference).

Run `codex` in your project and complete normal authentication. Never publish or replace `auth.json` as shared configuration. For connection problems, configure the [Mihomo proxy](mihomo.md#use-and-restart) first. If the site is unavailable, use the official installer URL and obtain both the generated TOML and model catalog from the operator through a trusted transfer.
