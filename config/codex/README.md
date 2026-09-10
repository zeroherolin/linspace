# Codex preset and catalog

| File | Purpose |
| --- | --- |
| [config.toml](config.toml) | Shared model, provider, context, reasoning, access and UI settings |
| [models-1m.json](models-1m.json) | Model-specific entries derived from the official Codex CLI catalog |
| [catalog-source.json](catalog-source.json) | Source version, export hash, intentional overrides and output hash |

## Catalog policy

The source CLI version and hashes are recorded in `catalog-source.json`. The generator reads `codex debug models --bundled`. Each model keeps its own official instructions, tool metadata, reasoning choices and service-tier metadata. Do not copy one model's prompts or capabilities into another entry.

Only these fields are overridden for this relay preset:

| Field | Value |
| --- | --- |
| `context_window` | 1,000,000 |
| `max_context_window` | 1,050,000 |
| `effective_context_window_percent` | 100 |

The official API pages list 1,050,000-token windows for [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol). The three overrides above set this preset’s 1M client budget rather than using the CLI’s bundled session limits. A catalog does not grant the relay capacity or model access. Keep CLI-advertised modes distinct from raw API reasoning parameters.

## Configuration

The preset covers the required model/catalog selection, provider and credential mode, HTTP Responses transport, reasoning, usable context, compaction, access policy and UI preferences. Compaction at 900,000 leaves 100,000 tokens below the configured client window. The TOML preset’s `xhigh` setting overrides the model catalog’s default reasoning level.

Credentials are supplied on the client. Optional retries, timeouts, storage, plugins, notifications and other features keep Codex defaults; they are not missing required settings. The preset selects an OpenAI-compatible provider, `on-request`/`auto_review` approvals and `danger-full-access`. Review these choices for the intended client environment. Fast service tiers are not forced by the TOML preset.

Check additional options against the [official schema](https://developers.openai.com/codex/config-schema.json) and installed CLI version. The [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) describes optional settings.

## Refresh and validate

From the repository root, using a reviewed official CLI version:

```sh
codex --version
python3 scripts/codex_catalog.py --refresh
./linspace check
```

Refresh regenerates the two entries and source record together, preserving all upstream fields except the three window overrides. It does not deploy. Review the version, instructions and capability changes before release. Offline builds check the catalog hash, unique model IDs, context bounds, advertised reasoning levels and the selected configuration's consistency. Full product-schema validation and real client tests are still part of a release review.

Client installation and relative file placement: [Codex guide](../../docs/usage/codex.md).
