# Mihomo bundle

Client proxy scripts for machines without access to the site. Run as root on Debian/Ubuntu, x86_64 or ARM64. Verify the archive against a trusted checksum before extraction.

## Install and import

From the extracted directory:

```sh
sha256sum --check SHA256SUMS
bash mihomo/install
bash mihomo/sub "$HOME/private-proxies.yaml"
```

Engine and GeoIP downloads use verified sources with automatic fallback; an existing trusted GeoIP file can be supplied with `--geoip-file /path/to/GeoIP.dat`. A successful import starts the proxy on `127.0.0.1:7890`:

```sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
```

## Restart and uninstall

```sh
bash mihomo/restart
bash mihomo/uninstall
```

Restart after a reboot or process exit; there is no autostart. Uninstall stops and removes Mihomo, services, settings and subscriptions; add `--dry-run` to preview and clear proxy variables afterward. Keep private subscriptions outside the bundle.
