# Mihomo target bundle

Run as root on Debian/Ubuntu, x86_64 or ARM64. Verify the archive against a trusted checksum before extraction, then run from the extracted bundle directory:

```sh
sha256sum --check SHA256SUMS
bash mihomo/install --geoip-file mihomo/assets/geoip-@@GEO_SHA@@.dat
bash mihomo/sub "$HOME/private-proxies.yaml"
bash mihomo/restart
```

The local GeoIP option avoids downloading it from https://@@DOMAIN@@. The pinned v1.19.27 engine still needs GitHub or a checksum-verified mirror. A successful subscription starts the proxy at `127.0.0.1:7890`; run restart after reboot or process exit. There is no autostart or supervisor.

Keep private subscription credentials outside this bundle and the public web root. This bundle contains only Mihomo tools and data. Other site features are distributed separately.
