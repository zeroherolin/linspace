# Codex

Run as the account that will use Codex on supported Linux or macOS. You need Bash, curl, tar, gzip and a SHA256 tool. Model access still requires your provider.

## Install and update

```sh
curl -fsSL https://your-domain.cn/codex/install | bash
export PATH="$HOME/.local/bin:$PATH"
codex --version
```

The script reuses a working same-version or newer installation. Otherwise it installs a reviewed native package, with verified download fallback. It never edits shell startup files or retains launcher backups. Rerun to update a linspace installation; update an older external installation with its original installer or package manager.

## Configure

These commands replace the current configuration. For a custom `CODEX_HOME`, see [configuration files](client-config.md).

```sh
install -d -m 700 ~/.codex
curl -fsSL https://your-domain.cn/codex/config -o ~/.codex/config.toml
chmod 600 ~/.codex/config.toml
```

Review the [preset](../../config/codex/config.toml) before applying it. It uses `gpt-6-astra`, `xhigh` reasoning, a 1M context budget, the OpenAI-compatible relay at `https://us.api.openai-next.com/v1`, and `danger-full-access` with `on-request` / `auto_review` approvals.

## Download the model catalog

```sh
curl -fsSL https://your-domain.cn/codex/models_1m -o ~/.codex/models-1m.json
chmod 600 ~/.codex/models-1m.json
```

Keep `models-1m.json` beside `config.toml`. The preset's relative `model_catalog_json` path needs no username replacement. Restart Codex after updating either file. The provider must support the selected model and context size. [Catalog details](../../config/codex/README.md).

## Authenticate

Enter your provider's API token at the hidden prompt:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash
```

Or pass it explicitly:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash -s -- -t 'YOUR_CODEX_TOKEN'
```

Replace the quoted placeholder; do not use angle brackets. The prompt avoids putting the token in shell history or command arguments.

To also change the relay URL:

```sh
curl -fsSL https://your-domain.cn/codex/auth | bash -s -- -t 'YOUR_CODEX_TOKEN' -u 'https://relay.example/v1'
```

`-u` replaces the existing `base_url` for the provider selected by `model_provider` in `config.toml`. Comments and other providers are preserved. **Omit `-u` to leave `config.toml` untouched.** Download the configuration first; invalid or unsupported configuration stops the update before credentials are changed.

The TOML parser is bundled. Missing Python is downloaded automatically on supported platforms. Updates use staged writes and retain no backups after success.

The script writes `auth.json` under `CODEX_HOME`, or `~/.codex` by default, with mode `600`. It replaces credentials only on the client and does not contact the provider to validate the token. The preset uses file-based credential storage; custom keyring or provider settings may use other credentials.

For ChatGPT account sign-in, use `codex login` instead. [Official authentication](https://learn.chatgpt.com/docs/auth).

## Use

From your project directory:

```sh
codex login status
codex
```

Login status confirms stored credentials, not provider access. If needed, [enable the proxy](mihomo.md#use-and-restart) before starting Codex.

## Uninstall

```sh
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```

Stops Codex and removes recognized CLI installations, settings and credentials, keeping only conversation history. [Scope and preview](uninstall.md).
