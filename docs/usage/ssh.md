# SSH public key

Run as the target account that should accept the key. You need Bash, curl, OpenSSH client tools and an SSH server allowing public-key authentication. Ask the operator for the public key URL and expected SHA256 fingerprint through a trusted channel.

The published name is configured by `ssh_public_key_name` (default `key.pub`). The examples below use `team.pub`; replace the domain and filename with the URL from `./linspace urls`. Names must start with an ASCII letter or digit, use only letters, digits, dots, underscores or hyphens, end in `.pub`, and be at most 128 characters. Paths are not accepted. An empty `ssh_public_key_file` disables publishing.

## Verify and import

Replace the domain and fingerprint. Download and verification failures leave `authorized_keys` unchanged.

```bash
(
    set -euo pipefail
    expected='SHA256:REPLACE_WITH_OPERATOR_FINGERPRINT'
    key_file=$(mktemp)
    trap 'rm -f "$key_file"' EXIT
    curl -q -fsSL --proto '=https' --proto-redir '=https' \
        https://your-domain.cn/ssh/team.pub -o "$key_file"
    fingerprint=$(ssh-keygen -lf "$key_file" -E sha256 | awk '{print $2}')
    [[ "$fingerprint" == "$expected" ]] || { echo 'Fingerprint mismatch' >&2; exit 1; }
    install -d -m 700 ~/.ssh
    touch ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    printf '\n%s\n' "$(cat "$key_file")" >> ~/.ssh/authorized_keys
)
```

This appends once; review existing entries and restrictions before repeating it. The endpoint exists only when the operator configured a public key. The operator can obtain the published fingerprint on the web host with:

```sh
ssh-keygen -lf /srv/linspace/current/ssh/team.pub -E sha256
```

## Test

On the client holding the matching private key:

```sh
ssh -i /path/to/private_key user@server
```

The private key stays on that client. Updating the key does not update existing `authorized_keys` files. Changing the published filename takes effect after deployment; clients must use the new URL.
