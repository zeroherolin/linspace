# Text stash

Eight channels, numbered **0–7**, each hold one UTF-8 file up to **1 MiB** (1,048,576 bytes), without NUL bytes. Uploads replace content. **Reads are public**; there is no history, expiry, or rate limit. Keep private data and credentials out.

Use Bash, curl and iconv on Linux or macOS. Replace `your-domain.cn` with the site domain.

## Upload

```sh
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- /path/to/text_file
```

The script prompts without echoing for the site's 48-character lowercase hexadecimal token. Change `7` to another channel; `/stash/upload` aliases channel 0. The same token authorizes all writes and clear.

For repeated uploads without putting the token in shell history:

```bash
read -rs -p 'Stash token: ' STASH_TOKEN
printf '\n'
export STASH_TOKEN
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- /path/to/text_file
unset STASH_TOKEN
```

`-t TOKEN` or `--token TOKEN` is also accepted after the filename, but literal arguments can appear in history/process listings. Clients send credentials to curl through stdin configuration.

## Read

```sh
curl -fsSL https://your-domain.cn/stash/download7
curl -fsSL https://your-domain.cn/stash/download7 -o received.txt
```

`/stash/download` aliases channel 0. Missing channels return 404; uploaded empty files return 200 with an empty body.

## Clear

```sh
curl -fsSL https://your-domain.cn/stash/clear | bash -s --
```

This clears **all eight channels**, using the same token prompt or environment variable. To empty one channel while keeping its URL present, upload an empty file there.

## Responses

| Request | Result |
| --- | --- |
| Authenticated PUT `/stash/download0` … `7` | 204; replaces one channel |
| Authenticated POST `/stash/clear` | 204; clears all channels |
| GET/HEAD of existing content | 200; plain text, `no-store`, `nosniff` |
| Missing or wrong write token | 401 |
| Over 1 MiB | 413 |
| NUL or invalid UTF-8 | 415 |
| Chunked or invalid-length PUT | 411 |

Invalid writes retain the previous file. Clients send a known content length; the writer treats missing `Content-Length` as zero. Caddy handles HTTPS/authentication and forwards writes to the Unix-socket service. See [architecture](../architecture.md) and [token operations](../operations.md#token).
