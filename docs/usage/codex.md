# Codex

Run as the account that will use Codex on supported Linux or macOS. You need Bash, curl and access to the site and your model provider.

## Install and update

```sh
curl -fsSL https://your-domain.cn/codex/install | bash
codex --version
```

The site redirects to the [official installer](https://learn.chatgpt.com/docs/codex/cli). Follow its PATH instructions. Run the same command again to update.

## Configure

These commands replace the current configuration. For backups or a custom `CODEX_HOME`, see [configuration files](client-config.md).

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

The script writes `auth.json` under `CODEX_HOME`, or `~/.codex` by default, with mode `600`. It backs up existing credentials and writes only on the client. It does not contact the provider to validate the token. The preset uses file-based credential storage; custom keyring or provider settings may use other credentials.

For ChatGPT account sign-in, use `codex login` instead. [Official authentication](https://learn.chatgpt.com/docs/auth).

## Use

From your project directory:

```sh
codex login status
codex
```

Login status confirms stored credentials, not provider access. If needed, [enable the proxy](mihomo.md#use-and-restart) before starting Codex.
