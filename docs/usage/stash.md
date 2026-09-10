# Text stash

Stash has eight channels, **0–7**. Each holds one UTF-8 file up to **1 MiB**, without NUL bytes. Upload replaces the previous file. Reads are public, with no history or expiry; keep secrets out.

Clients need Bash, curl and OpenSSH 8.2+ on Linux or macOS. Missing Python is downloaded automatically on supported platforms. Runtime downloads need tar, gzip and a SHA256 tool. Upload and clear require an authorized private key or agent.

## Upload

```sh
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- 'file.txt'
```

Change `7` to another channel. `/stash/upload` is an alias for channel 0. Normally no token or `-i` is needed.

## Read

```sh
curl -fsSL https://your-domain.cn/stash/download7
curl -fsSL https://your-domain.cn/stash/download7 -o received.txt
```

`/stash/download` is an alias for channel 0. A missing channel returns 404; an empty uploaded file returns 200.

## Clear

```sh
curl -fsSL https://your-domain.cn/stash/clear | bash
```

This removes **all eight channels**. To empty only one channel while keeping its URL available, upload an empty file there.

## Choose a key

The client first matches keys in `ssh-agent`, then standard `~/.ssh/id_*` key pairs, then other `.pub` files with a private file beside them. Private keys never leave the client.

Encrypted keys may need a passphrase; hardware keys may need a touch. Load a key into your existing agent for repeated use:

```sh
ssh-add ~/.ssh/id_ed25519
```

For a key outside `~/.ssh`, set its path once in your shell profile:

```sh
export STASH_IDENTITY=/path/to/private_key
```

A one-command `-i /path/to/private_key` override is also supported. A `.pub` path works when its private key is in the agent.

**A public key in `authorized_keys` cannot sign uploads.** On a remote machine, authorize that machine's own public key or use an agent available in a trusted session. [Manage site authorization](../operations.md#stash-authorized-keys).

## Troubleshooting

| Result | Action |
| --- | --- |
| No authorized identity | Load the key into the agent or ask the operator to authorize it |
| Writes disabled | The site has no authorized public keys |
| 401 | Download the current script and retry; the signature may be invalid, expired or already used |
| 429 / 503 | Retry later; the operator should check service logs |
| 413 / 415 | Use UTF-8 text without NUL bytes, at most 1 MiB |
| 411 | Upload with the current script, which sends the required Content-Length |

Successful writes return 204. Legacy Stash tokens are no longer accepted. [Authentication protocol](../stash-auth.md).
