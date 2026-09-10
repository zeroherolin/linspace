# SSH access

Run as the account that should accept SSH logins. It needs an SSH server with public-key authentication enabled. Ask the operator for the published filename and expected SHA256 fingerprint.

## Verify and import

Replace the domain and `team.pub` with the site's values.

```sh
install -d -m 700 ~/.ssh
curl -fsSL https://your-domain.cn/ssh/team.pub -o ~/.ssh/linspace-site.pub
ssh-keygen -lf ~/.ssh/linspace-site.pub -E sha256
```

Stop if the download fails or the fingerprint does not match. Once verified, append the key once:

```sh
echo >> ~/.ssh/authorized_keys
cat ~/.ssh/linspace-site.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

This preserves existing keys. Check for an existing entry and any access restrictions before repeating the import.

## Connect

From the machine holding the matching private key or agent:

```sh
ssh user@server
```

For a nonstandard private-key path:

```sh
ssh -i /path/to/private_key user@server
```

Importing a public key permits incoming login; it does not give the target machine signing credentials for [Stash](stash.md).

## Operator settings

`ssh_public_key_file` selects the key. `ssh_public_key_name` selects its URL filename and defaults to `key.pub`. An empty source path disables publishing.

Published filenames must start with a letter or digit, contain only ASCII letters, digits, dots, underscores or hyphens, end in `.pub`, and be at most 128 characters.

Read the active key's fingerprint on the web server:

```sh
ssh-keygen -lf /srv/linspace/current/ssh/team.pub -E sha256
```

Changing the published key does not update existing `authorized_keys` files. Changing its filename changes the download URL.
