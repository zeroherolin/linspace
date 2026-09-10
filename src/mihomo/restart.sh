#!/usr/bin/env bash
@@include:src/common/ui.sh@@
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[[ $EUID -eq 0 ]] || { linspace_log ERROR 'run this script as root.'; exit 1; }
[[ -f /usr/local/lib/linspace-mihomo/process.py ]] || { linspace_log ERROR 'run install first.'; exit 1; }
umask 077
[[ -d /run/lock ]] || install -d -m 755 /run/lock
exec 9>/run/lock/linspace-mihomo.lock
flock -n 9 || { linspace_log ERROR 'another installation, update, or restart is running.'; exit 1; }
python=/usr/local/lib/linspace-mihomo/python
[[ -x $python ]] || python=/usr/bin/python3
exec "$python" /usr/local/lib/linspace-mihomo/process.py restart
