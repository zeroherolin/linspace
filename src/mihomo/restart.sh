#!/usr/bin/env bash
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID -eq 0 ]] || { printf 'Error: run this script as root.\n' >&2; exit 1; }
[[ -f /usr/local/lib/linspace-mihomo/process.py ]] || { printf 'Error: run install first.\n' >&2; exit 1; }
umask 077
[[ -d /run/lock ]] || install -d -m 755 /run/lock
exec 9>/run/lock/linspace-mihomo.lock
flock -n 9 || { printf 'Error: another installation, update, or restart is running.\n' >&2; exit 1; }
python=/usr/local/lib/linspace-mihomo/python
[[ -x $python ]] || python=/usr/bin/python3
exec "$python" /usr/local/lib/linspace-mihomo/process.py restart
