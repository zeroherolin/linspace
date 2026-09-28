#!/bin/sh
set -eu
/usr/bin/sha256sum --check /usr/local/lib/linspace-mihomo/geoip.sha256
/usr/local/bin/mihomo -t -d /var/lib/mihomo -f /etc/mihomo/config.yaml
exec /usr/local/bin/mihomo -d /var/lib/mihomo -f /etc/mihomo/config.yaml
