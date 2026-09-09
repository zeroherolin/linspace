# mihomo target bundle

These self-contained scripts use https://@@DOMAIN@@ for the pinned GeoIP download.
On a Debian/Ubuntu target, as root:

```sh
sha256sum --check SHA256SUMS
bash mihomo/install --geoip-file mihomo/assets/geoip-@@GEO_SHA@@.dat
bash mihomo/sub /root/private-proxies.yaml
bash mihomo/restart
```

The local GeoIP option avoids the site download. The pinned engine is still
fetched from GitHub or a checksum-verified mirror. The proxy listens on
127.0.0.1:7890 and has no automatic startup. Subscription files contain private
node credentials; keep them outside this public bundle and the web root.
