# Install and use mihomo

Ask the site operator for the base URL and replace `your-domain.cn` in the examples. The operator can run `./linspace urls` from the repository checkout; the target machine does not need a checkout.

Run the commands in this guide as **root on a Debian/Ubuntu target**, on x86_64 or ARM64. mihomo runs as an ordinary background process under its own account. There is no systemd service, Supervisor process, watchdog, or automatic startup. Run `restart` after an exit, host reboot, or container restart.

## Requirements

The target needs access to `https://your-domain.cn` and the engine download sources. The installer tries GitHub first, then `gh-proxy.com` and `ghfast.top`, and checks the same pinned SHA256 for every source. Engine downloads ignore proxy environment variables. Missing packages, including curl, CA certificates, gzip, Python, and `python3-yaml`, are installed through apt.

An old or unmanaged mihomo installation must be backed up and removed first. The installer rejects existing `/etc/systemd/system/mihomo.service`, `/etc/mihomo/supervisord.conf`, or an unrecognized managed installation marker.

## Install

```sh
curl -fsSL https://your-domain.cn/mihomo/install | bash
```

To review a script before running it, replace `| bash` with `| less`.

The installer fetches and verifies mihomo **v1.19.27** and the pinned GeoIP snapshot, creates the dedicated `mihomo` system account, and installs the baseline and process-management files. A fresh install does not create `/etc/mihomo/config.yaml` or start a proxy. The first successful `sub` creates the runtime configuration and node file and starts the process.

Rerunning `install` on a recognized installation validates and preserves the current configuration, nodes, and process state. For a site-unavailable installation, see [the target bundle procedure](#use-a-target-bundle).

## Import or update a subscription

`sub` takes exactly one argument: an HTTPS subscription URL or a local YAML path. It requires Clash/mihomo YAML with a nonempty `proxies` array. It imports only the nodes, preserving their fields and order. Subscription rules, policy groups, DNS, and listener settings are not imported. Provider-only subscriptions are unsupported.

```sh
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s 'https://subscription.example/your-path'
# Or use a local private YAML file, preferably mode 0600:
curl -fsSL https://your-domain.cn/mihomo/sub | bash -s /root/private-proxies.yaml
```

Keep the URL in single quotes so `&` and `?` are not interpreted by the shell. The example domain is a placeholder.

The update process:

1. Downloads directly first. If that fails and a managed proxy is already running, retries through `127.0.0.1:7890`.
2. Checks nodes in subscription order with verified HTTPS to `https://www.google.com`, requiring HTTP 200. It selects the first passing node, not the lowest-latency node.
3. Stages and verifies the new configuration, then replaces the managed configuration and selection cache. A failed update retains or restores the previous files and process state.
4. Saves the previous private configuration under `/var/lib/mihomo/backup-*`.

Selection happens when `sub` runs. The default group does not automatically switch nodes during normal operation.

## Use the proxy

```sh
curl -fsSI --connect-timeout 5 --max-time 15 \
    --noproxy '' --proxy http://127.0.0.1:7890 https://www.google.com
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
```

The test should return HTTP 200. The HTTP/SOCKS mixed listener binds only to `127.0.0.1:7890`. These environment variables affect programs in the current shell that read them; they do not redirect all system traffic or enable TUN. Other accounts on the same host can also use the loopback listener.

## Restart, status, and logs

```sh
curl -fsSL https://your-domain.cn/mihomo/restart | bash
python3 /usr/local/lib/linspace-mihomo/process.py status
tail -n 50 /var/log/mihomo/mihomo.log
curl -fsS --noproxy '*' --unix-socket /run/mihomo/control.sock http://localhost/proxies/PROXY
```

`restart` checks the recorded PID identity, stops the old managed process if present, and starts it again with the existing configuration and selection. The API response's `now` field identifies the selected node.

## Runtime policy

| Setting | Behavior |
| --- | --- |
| Routing | `GEOIP,CN,DIRECT`, then `MATCH,PROXY` |
| Default group | `PROXY`, a `select` group chosen by `sub` |
| Separate group | `AUTO`, an independent `url-test` group |
| Health checks | Every 300 seconds using `http://www.gstatic.com/generate_204` |
| Import probe | Verified HTTPS to `https://www.google.com`, HTTP 200 |
| Updates | Pinned engine and GeoIP; no automatic subscription or GeoIP updates |
| Control API | `/run/mihomo/control.sock` in a private runtime directory |
| Disabled features | TUN, built-in DNS, and sniffing |
| Node validation | Nodes that request skipping TLS certificate verification are rejected |

Actual reachability and egress still depend on node parameters, DNS, and network conditions.

## Files on the target

| Path | Contents |
| --- | --- |
| `/usr/local/bin/mihomo` | Pinned engine |
| `/etc/mihomo/config.yaml` | Runtime configuration created by the first successful import |
| `/var/lib/mihomo/` | `proxies.yaml`, `GeoIP.dat`, `cache.db`, and private `backup-*` directories |
| `/usr/local/lib/linspace-mihomo/` | `process.py`, `run-mihomo.sh`, `baseline.yaml`, `geoip.sha256`, and the managed marker |
| `/run/linspace-mihomo/process.json` | Root-only PID and process-start identity record |
| `/run/mihomo/control.sock` | Local control API |
| `/var/log/mihomo/mihomo.log` | Background log |

At startup, a log larger than 5 MiB is rotated with `.1` through `.3` retained. The process does not rotate logs while running; use an appropriate host log-rotation policy for long-lived processes. Configuration backups contain node credentials and should be cleaned up deliberately.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| A message says to run as root | Switch to root or use `sudo bash` at the execution end of the pipeline |
| Older or unmanaged installation detected | Back up and uninstall the old setup first |
| No engine source passes download/checksum checks | Check outbound access to GitHub and both mirrors; retry after a network or mirror problem is resolved |
| Proxy unavailable after reboot | Run `restart`; there is no automatic startup |
| Direct subscription download fails and no existing proxy is running | Obtain the YAML through another connection and import the local file |
| Another installation/update/restart is running | Wait for the operation holding the lock to finish |
| Process is not ready | Check the log, configuration, listener conflicts, and control socket |

Canonical implementation: [src/mihomo](../../src/mihomo).

## Use a target bundle

On the build machine, from the repository root, create the target bundle and its checksum sidecar:

```sh
./linspace build
awk '$2 == "linspace-mihomo-target.tar.gz" { print }' dist/SHA256SUMS > dist/linspace-mihomo-target.tar.gz.sha256
```

Transfer both files through a trusted channel. On the target, start in the directory containing them and run as root:

```sh
sha256sum --check linspace-mihomo-target.tar.gz.sha256
target_dir=$(mktemp -d ./linspace-target.XXXXXX)
tar --no-same-owner -xzf linspace-mihomo-target.tar.gz -C "$target_dir"
cd "$target_dir/linspace-mihomo-target"
```

Then install and import your private nodes:

```sh
sha256sum --check SHA256SUMS
bash mihomo/install --geoip-file mihomo/assets/geoip-*.dat
bash mihomo/sub /root/private-proxies.yaml
bash mihomo/restart
```

The bundle contains exactly one pinned GeoIP file. The local-file option avoids
its site download; the pinned engine is still downloaded from GitHub or the
configured mirrors. Keep private subscription files outside the public bundle.
