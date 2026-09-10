# Codex preset and catalog

| File | Purpose |
| --- | --- |
| [config.toml](config.toml) | Shared model, provider, context and client preferences |
| [models-1m.json](models-1m.json) | Model-specific entries from the official Codex CLI |
| [catalog-source.json](catalog-source.json) | Source version, export hash, overrides and output hash |

For client commands, use the [Codex guide](../../docs/usage/codex.md).

## Catalog policy

Each model retains its own official instructions, capabilities, reasoning choices and service-tier metadata. Only these fields are overridden:

| Field | Value |
| --- | --- |
| `context_window` | 1,000,000 |
| `max_context_window` | 1,050,000 |
| `effective_context_window_percent` | 100 |

The API pages for [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) describe 1,050,000-token windows. These overrides set the client's 1M budget; they do not grant provider capacity or model access.

## Configuration

The preset compacts at 900,000 tokens, uses `xhigh` reasoning and selects an OpenAI-compatible relay. It uses `on-request` / `auto_review` approvals and `danger-full-access`; review these preferences for each client.

`cli_auth_credentials_store = "file"` keeps API credentials in the client's `auth.json`. Credentials are never bundled. Optional retries, timeouts, plugins and notifications keep Codex defaults. No fast service tier is forced.

Check additional settings against the installed CLI and the [official schema](https://developers.openai.com/codex/config-schema.json). [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Refresh and validate

From the repository root, using a reviewed official CLI version:

```sh
codex --version
python3 scripts/codex_catalog.py --refresh
./linspace check
```

Refresh reads `codex debug models --bundled` and updates both model entries and the source record. Review the version, instructions and capabilities before deployment.

Offline builds check hashes, model IDs, context bounds, reasoning levels and TOML consistency. Real client tests and full product-schema validation remain part of release review.
