#!/usr/bin/env bash
# Install the official stable Debian/Ubuntu Caddy package when absent.
set -Eeuo pipefail
[[ $EUID -eq 0 && -f /etc/debian_version ]] || { echo 'Run as root on Debian/Ubuntu.' >&2; exit 1; }
if command -v caddy >/dev/null; then exit 0; fi
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg debian-keyring debian-archive-keyring apt-transport-https
curl -q -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 120 https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -q -fsSL --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 120 https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
chmod 644 /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y --no-install-recommends caddy
