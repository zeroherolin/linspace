# Mihomo

Run as **root on Debian/Ubuntu**, x86_64 or ARM64. Replace `your-domain.cn` with your site domain. Install this on the client that needs a proxy.

## Install

```sh
curl -fsSL https://your-domain.cn/mihomo/install | bash
```

This installs pinned Mihomo **v1.19.27**, GeoIP and its Python runtime when needed. Failed downloads automatically use a verified download fallback. A fresh install starts nothing until you import a subscription.

Rerunning install preserves a recognized linspace configuration. Back up and remove an unmanaged or supervised Mihomo installation before switching to this installer.

## Import nodes

Use an HTTPS Clash/mihomo YAML subscription:

```sh
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s -- 'https://subscription.example/your-path'
```

Or a local YAML file:

```sh
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s -- "$HOME/private-proxies.yaml"
```

The YAML must contain a nonempty `proxies` array. Only nodes are imported; provider-only subscriptions and nodes that disable TLS verification are rejected.

Import selects the first working node, starts the proxy and backs up any previous configuration. Failure preserves or restores the previous state. Keep subscriptions private.

## Use and restart

Enable the proxy in the terminal running your client:

```sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
curl -fsSI --proxy http://127.0.0.1:7890 --noproxy '' https://www.google.com
```

The listener is local to the machine. Rules send China IPs directly and other traffic through the selected proxy. These variables affect programs that honor proxy settings.

After reboot, container restart or process exit:

```sh
curl -fsSL https://your-domain.cn/mihomo/restart | bash
```

Restart preserves the configuration and node selection. There is no autostart, watchdog or automatic failover.

## Diagnose

```sh
/usr/local/lib/linspace-mihomo/python /usr/local/lib/linspace-mihomo/process.py status
tail -n 50 /var/log/mihomo/mihomo.log
```

Configuration is in `/etc/mihomo/config.yaml`; nodes, GeoIP and backups are under `/var/lib/mihomo/`. The control socket is `/run/mihomo/control.sock`. TUN, built-in DNS, sniffing and automatic updates are disabled.

## Use a target bundle

If site downloads are unavailable, ask the operator for `linspace-mihomo-target.tar.gz` and its trusted SHA256. Verify the archive, extract it to an empty directory and follow its [README](../../packaging/mihomo-README.md).

The bundle contains the client scripts. Engine and GeoIP downloads use the same automatic fallback. Keep private subscriptions outside the bundle.
