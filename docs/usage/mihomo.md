# Mihomo

Run as **root on a Debian/Ubuntu target**, x86_64 or ARM64. Replace `your-domain.cn` with your site domain. The web server only publishes these tools; it does not need a proxy installation.

## Install

```sh
curl -fsSL https://your-domain.cn/mihomo/install | bash
```

The script installs missing apt dependencies, downloads pinned **v1.19.27** and GeoIP, and creates the dedicated `mihomo` account. Engine downloads try GitHub, then `gh-proxy.com` and `ghfast.top`, with the same pinned checksum. Downloads ignore proxy environment variables. The target needs access to those sources and the site; slow direct transfers can time out.

A fresh install starts nothing until a subscription is imported. Rerunning install preserves a recognized managed configuration and its running state. Back up and remove an unmanaged or supervised installation before switching to these scripts.

## Import nodes

Use an HTTPS Clash/mihomo YAML subscription or a private local YAML file:

```sh
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s 'https://subscription.example/your-path'
# Or:
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s "$HOME/private-proxies.yaml"
```

The file needs a nonempty `proxies` array. Only node definitions are imported, preserving fields and order; provider-only subscriptions and nodes disabling TLS verification are rejected. Keep URLs and node credentials private.

The importer downloads directly, then retries through an existing managed proxy if needed. It selects the first node in subscription order that passes verified HTTPS to Google with HTTP 200. Success starts/replaces the managed configuration and saves a private backup under `/var/lib/mihomo/backup-*`; failure preserves or restores the prior configuration and running state.

## Use and restart

```sh
curl -fsSI --connect-timeout 5 --max-time 15 \
    --noproxy '' --proxy http://127.0.0.1:7890 https://www.google.com
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
```

Expect HTTP 200. The mixed HTTP/SOCKS listener binds only to `127.0.0.1:7890`; other local accounts can use it. Environment variables affect only programs that honor them, not all host traffic.

```sh
curl -fsSL https://your-domain.cn/mihomo/restart | bash
python3 /usr/local/lib/linspace-mihomo/process.py status
tail -n 50 /var/log/mihomo/mihomo.log
curl -fsS --noproxy '*' --unix-socket /run/mihomo/control.sock http://localhost/proxies/PROXY
```

Restart retains the configuration and selection. There is **no service, watchdog, or autostart**; run it after reboot, container restart, or process exit. A deployment/update lock rejects overlapping operations.

## Runtime policy and files

| Setting | Value |
| --- | --- |
| Rules | `GEOIP,CN,DIRECT`, then `MATCH,PROXY` |
| `PROXY` | Manual selection chosen by `sub`; no automatic failover |
| `AUTO` | Separate `url-test` group |
| Health checks | Every 300 seconds via `http://www.gstatic.com/generate_204` |
| Control API | Private `/run/mihomo/control.sock` |
| TUN, built-in DNS, sniffing | Disabled |
| Automatic engine/GeoIP/subscription updates | Disabled |

The binary is `/usr/local/bin/mihomo`; configuration is `/etc/mihomo/config.yaml`. Nodes, GeoIP, cache and backups live in `/var/lib/mihomo/`; management scripts in `/usr/local/lib/linspace-mihomo/`. PID identity is recorded in `/run/linspace-mihomo/process.json`. Logs rotate at startup above 5 MiB, retaining three copies; arrange host log rotation for long-running processes.

## Use a target bundle

Use this when site downloads are unavailable or too slow. On the build machine, from the repository root:

```sh
./linspace build
awk '$2 == "linspace-mihomo-target.tar.gz" { print }' dist/SHA256SUMS > dist/linspace-mihomo-target.tar.gz.sha256
```

Transfer both files through a trusted channel. On the target, from their directory:

```sh
sha256sum --check linspace-mihomo-target.tar.gz.sha256
target_dir=$(mktemp -d ./linspace-target.XXXXXX)
tar --no-same-owner -xzf linspace-mihomo-target.tar.gz -C "$target_dir"
cd "$target_dir/linspace-mihomo-target"
sha256sum --check SHA256SUMS
bash mihomo/install --geoip-file mihomo/assets/geoip-*.dat
bash mihomo/sub "$HOME/private-proxies.yaml"
bash mihomo/restart
```

The bundle has exactly one pinned GeoIP file. `--geoip-file` skips only its site download; the engine still needs GitHub or a mirror. Keep private subscriptions outside this public bundle. Source: [src/mihomo](../../src/mihomo).
