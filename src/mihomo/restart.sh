#!/usr/bin/env bash
@@include:src/common/ui.sh@@
# Restart the managed Mihomo process. Keep the selected proxy while it works; otherwise
# select the first working proxy of the imported subscription, in order, as import does.
# Usage: curl -fsSL https://@@DOMAIN@@/mihomo/restart | bash
main() (
    set -Eeuo pipefail
    export PATH=/usr/sbin:/usr/bin:/sbin:/bin
    umask 077
    case ${1:-} in
        -h|--help)
            printf 'Usage: bash restart\nRestarts mihomo and keeps the selected proxy while it passes the HTTPS check; otherwise selects the first working proxy of the imported subscription, in order.\n'
            exit 0 ;;
    esac
    [[ $# -eq 0 ]] || { linspace_log ERROR 'This script takes no arguments.'; exit 1; }
    [[ $EUID -eq 0 ]] || { linspace_log ERROR 'run this script as root.'; exit 1; }
    [[ -f /usr/local/lib/linspace-mihomo/process.py && -f /usr/local/lib/linspace-mihomo/vendor.zip ]] || { linspace_log ERROR 'run install first.'; exit 1; }
    python=/usr/local/lib/linspace-mihomo/python
    [[ -x $python ]] || python=/usr/bin/python3
    # The embedded import tool takes the shared operation lock itself.
    "$python" - --reselect <<'LINSPACE_SUB_PY'
import sys
sys.path.insert(0, '/usr/local/lib/linspace-mihomo/vendor.zip')
@@include:src/mihomo/sub.py@@
LINSPACE_SUB_PY
)
main "$@"
