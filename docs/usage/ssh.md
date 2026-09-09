# Import the SSH public key

This endpoint exists only when the site operator configured a public key. Ask the operator for the base URL and the expected SHA256 fingerprint through a trusted channel. The operator can run `./linspace urls` from the repository checkout; clients do not need to clone the repository.

Run the following commands in Bash as the account that should accept the key on the target host. Root is needed only when configuring the root account. The SSH server must allow public-key authentication, and the target needs curl and OpenSSH client tools.

## Download, verify, and import

Replace the domain and `EXPECTED_FINGERPRINT` below. The procedure downloads once, checks that exact file, and then appends it. A download or fingerprint failure leaves `authorized_keys` unchanged.

```bash
(
    set -euo pipefail
    EXPECTED_FINGERPRINT='SHA256:REPLACE_WITH_OPERATOR_FINGERPRINT'
    key_file=$(mktemp)
    trap 'rm -f "$key_file"' EXIT
    curl -q -fsSL --proto '=https' --proto-redir '=https' \
        https://your-domain.cn/ssh/key.pub -o "$key_file"
    fingerprint=$(ssh-keygen -lf "$key_file" -E sha256 | awk '{print $2}')
    if [[ "$fingerprint" != "$EXPECTED_FINGERPRINT" ]]; then
        printf 'Fingerprint mismatch: %s\n' "$fingerprint" >&2
        exit 1
    fi
    install -d -m 700 ~/.ssh
    touch ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    printf '\n%s\n' "$(cat "$key_file")" >> ~/.ssh/authorized_keys
)
```

The leading newline prevents a key from being joined to an existing unterminated line. This is an append operation, not an idempotent key manager: run it once per new key. Review existing matching entries and any key restrictions before adding or replacing them.

On the web host, the operator can obtain the published fingerprint with:

```sh
ssh-keygen -lf /srv/linspace/current/ssh/key.pub -E sha256
```

## Test the login

On the client holding the matching private key, replace the path, account, and host:

```sh
ssh -i /path/to/private_key user@server
```

The private key stays on that client. Updating the public key on the website does not update any account's `authorized_keys`. Deployment itself does not grant SSH access to the web host.
