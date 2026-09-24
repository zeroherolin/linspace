# Linspace Complete Help

Every client command for this site. Linux or macOS with Bash and curl; run as your own account unless a section says otherwise, and stop if a command fails. Configuration downloads replace existing files.

## SSH key

Import the site's public key to allow logins with the matching private key. Confirm the fingerprint with the operator through another channel before authorizing it.

```sh
install -d -m 700 ~/.ssh
curl -fsSL https://your-domain.cn/ssh/your-key.pub -o ~/.ssh/linspace-site.pub
ssh-keygen -lf ~/.ssh/linspace-site.pub -E sha256
```

Stop if the fingerprint differs. Otherwise append the key once:

```sh
echo >> ~/.ssh/authorized_keys
cat ~/.ssh/linspace-site.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

## Mihomo

Run as root on a Debian or Ubuntu client. The subscription stays private on that machine, and nothing starts until one is imported.

```sh
curl -fsSL https://your-domain.cn/mihomo/install | bash
curl -fsSL https://your-domain.cn/mihomo/sub | bash
```

The import command asks for the subscription address without echo, accepts a URL or a local file, selects a working node and starts the proxy on `127.0.0.1:7890`. Use it from the terminal running your client:

```sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
curl -fsSI --proxy http://127.0.0.1:7890 --noproxy '' https://www.google.com
```

Restart after a reboot or when the selected node stops working; nothing is downloaded:

```sh
curl -fsSL https://your-domain.cn/mihomo/restart | bash
```

Configuration is `/etc/mihomo/config.yaml`; nodes and GeoIP are under `/var/lib/mihomo/`.

@@include:docs/help.md#tmux@@

@@include:docs/help.md#Claude Code@@

@@include:docs/help.md#Codex@@

## Stash

Eight public text channels, `0` through `7`. Reads are public with no history or expiry, so keep secrets out; writes need a private key whose public key the operator has authorized.

```sh
curl -fsSL https://your-domain.cn/stash/upload7 | bash -s -- 'file.txt'
curl -fsSL https://your-domain.cn/stash/download7 -o received.txt
curl -fsSL https://your-domain.cn/stash/clear | bash
```

`upload` and `download` without a digit mean channel 0. Each channel holds one UTF-8 file up to 1 MiB; an upload replaces the previous file, and a missing channel returns 404.

The client tries `ssh-agent`, then key pairs under `~/.ssh`. Use `ssh-add` for encrypted keys, `-i /path/to/private_key` for a one-off key, or `export STASH_IDENTITY=/path/to/private_key` for a persistent one.

## Uninstall

Run only the command for the tool you want to remove; the Mihomo command needs root. **Only Claude Code and Codex session records are kept.** Settings, credentials, plugins, skills and other client data are deleted without backups; removing tmux also deletes `~/.tmux.conf`, and Mihomo retains nothing.

```sh
curl -fsSL https://your-domain.cn/mihomo/uninstall | bash
curl -fsSL https://your-domain.cn/tmux/uninstall | bash
curl -fsSL https://your-domain.cn/claude/uninstall | bash
curl -fsSL https://your-domain.cn/codex/uninstall | bash
```

Add `-s -- --dry-run` after `bash` to preview. Close all tmux sessions before removing tmux. After removing Mihomo, run `unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY`. Project files and shell startup files are untouched.
