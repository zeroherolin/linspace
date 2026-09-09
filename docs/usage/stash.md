# Use the text stash

Ask the site operator for the base URL and replace `your-domain.cn` in the examples. The operator can run `./linspace urls` from the repository checkout; clients do not need a checkout.

Stash provides eight channels, numbered 0 through 7. Each channel holds one complete UTF-8 text file. Writers need a token; **anyone can read every channel** at a fixed URL. An upload replaces the previous content, with no version history. Content remains until it is overwritten or cleared; it does not expire automatically.

Use any account on Linux or macOS with Bash, curl, and iconv. Files must contain valid UTF-8, contain no NUL bytes, and be at most 1 MiB (1,048,576 bytes). The client and server both check content constraints.

## Upload

Write a local file to channel 7:

```sh
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- /path/to/text_file
```

Use the complete generated token: 48 lowercase hexadecimal characters. The script prompts for it on the terminal without echoing it. `upload0` through `upload6` select the other channels, and `upload` is an alias for `upload0`.

For repeated use in a Bash shell, read the token without putting it into shell history:

```bash
read -rs -p 'Stash token: ' STASH_TOKEN
printf '\n'
export STASH_TOKEN
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- /path/to/text_file
unset STASH_TOKEN
```

The client also supports `-t TOKEN` or `--token TOKEN` after the filename. The `--` immediately after `bash -s` ensures the script receives options such as `-t`, instead of Bash interpreting them.

The client passes its token to curl through stdin configuration. A literal token entered as a shell argument can still appear in shell history or the Bash process arguments; use the prompt or environment-variable interface when that matters.

Success prints `Uploaded N bytes` and the public download URL. Invalid text, excess size, a rejected token, and other failures produce an `Error:` message and a nonzero exit code.

## Read

```sh
curl -fsSL https://your-domain.cn/stash/download7
curl -fsSL https://your-domain.cn/stash/download7 -o received.txt
```

`download` aliases channel 0. An absent channel returns 404; `curl -f` exits with code 22. A channel containing an uploaded empty file exists and returns an empty body.

## Clear

This clears **all eight channels**, using the same token prompt or `STASH_TOKEN` environment variable:

```sh
curl -fsSL https://your-domain.cn/stash/clear | bash -s --
```

To replace only one channel's content with an empty file, upload an empty file to that channel. That leaves an existing empty channel; it does not make the channel return 404.

## Request behavior

| Operation | Result |
| --- | --- |
| Authenticated PUT `/stash/download0` through `/stash/download7` | 204 after a successful replacement |
| Authenticated POST `/stash/clear` | 204 after removing the eight channel files |
| GET/HEAD of a populated channel | Public, `text/plain; charset=utf-8`, `nosniff`, `no-store` |
| Missing/incorrect write token | 401 from Caddy |
| Too much data | 413 |
| NUL bytes or invalid UTF-8 | 415 |
| Chunked or invalid-length PUT to the writer | 411 |

Clients send a known content length. The writer treats a missing `Content-Length` as zero and rejects invalid lengths or chunked requests.

Caddy handles TLS, bcrypt Basic authentication (username `stash`), request-size limits, and public reads. Caddy forwards writes through a permission-restricted Unix socket. The writer itself does not authenticate tokens; it validates the body and writes via a temporary file, `fsync`, and rename, so readers see a complete old or new file.

There is no uploader identity history, automatic cleanup, or rate limit in the implementation. Keep credentials and anything private out of channels. Token rotation and diagnostics are in [operations](../operations.md).
