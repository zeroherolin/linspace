# Mihomo target bundle

Run as root on Debian/Ubuntu, x86_64 or ARM64. Verify the archive against a trusted checksum before extraction.

## Install and import

From the extracted bundle directory:

```sh
sha256sum --check SHA256SUMS
bash mihomo/install --geoip-file mihomo/assets/geoip-*.dat
bash mihomo/sub "$HOME/private-proxies.yaml"
```

The bundle contains one GeoIP file. This avoids fetching it from `https://@@DOMAIN@@`; the pinned v1.19.27 engine still needs GitHub or a checksum-verified mirror.

Successful import starts the proxy on `127.0.0.1:7890`. To use it in the current terminal:

```sh
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
```

## Restart

```sh
bash mihomo/restart
```

Run after reboot or process exit. There is no autostart or supervisor. Keep private subscriptions outside the bundle and public web root. This bundle contains only Mihomo tools and data.
