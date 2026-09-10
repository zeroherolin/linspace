# Stash authentication protocol

Stash uses [OpenSSH SSHSIG signatures](https://man.openbsd.org/ssh-keygen.1#Y~3) over HTTPS. Caddy limits request bodies; `stashd` verifies every write, including direct Unix-socket requests. No SSH login, extra TCP port or shared client token is needed.

## Request flow

1. GET `/stash/keys` returns authorized public keys for client discovery.
2. GET `/stash/challenge` returns an opaque challenge valid for 90 seconds. HEAD checks availability without issuing one.
3. Sign the message below using namespace `linspace-stash@DOMAIN`.
4. Send PUT `/stash/downloadN` with the file bytes, or POST `/stash/clear` with an empty body.

Both writes carry `X-Linspace-Challenge` and `X-Linspace-Signature`. The latter is standard Base64 of the complete ASCII-armored SSH signature.

The signed message is ASCII with LF separators and a final LF:

```text
linspace-stash-v1
https://DOMAIN
METHOD
/stash/downloadN
LOWERCASE_SHA256_OF_BODY
CHALLENGE
```

For clear, use `POST`, `/stash/clear` and the empty-body digest. The configured hostname defines the audience, not the request Host header. Write paths reject queries, alternate encodings and absolute-form targets. Clients do not follow redirects with signed requests.

## Authorization and replay protection

The build emits a root-owned `allowed_signers` file for up to 64 keys, restricted to the site's namespace and the `stash` principal. `ssh-keygen -Y verify` checks this allowlist. All authorized keys have equal upload/clear access; a client-supplied public key cannot authorize itself.

A challenge contains 32 random bytes, an expiry and HMAC-SHA256 using a per-process random secret. Issuance allocates no persistent state. After verification, a locked replay map consumes the challenge once, including concurrent duplicates. Restarts replace the secret and invalidate old challenges. Clients need no synchronized clock.

| Bound | Limit |
| --- | --- |
| Challenge lifetime | 90 seconds |
| Used challenges | 8,192; expired entries are removed |
| Concurrent verifications | 4 |
| Verification subprocess | 5 seconds |
| Active connections | 32 |

Invalid, expired or replayed authorization returns 401. Exhausted verification/replay capacity returns 429; transient verification failures return 503. These bounds are not a per-user rate limiter.

## Writes and migration

Uploads replace files atomically; clear is sequential across channels. After a lost success response, inspect the channel before retrying.

Legacy Basic authentication is rejected. The SSH writer uses `/run/stashd/ssh.sock`, distinct from the legacy socket, so old in-flight proxy requests cannot reach the other authentication mode. Deployment and rollback also pause writes during activation. [Recovery](deployment.md#failure-and-recovery).
