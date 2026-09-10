#!/usr/bin/env bash
@@include:src/common/ui.sh@@
# Usage: curl -fsSL https://@@DOMAIN@@/stash/clear | bash
main() (
set -Eeuo pipefail
@@include:src/common/download.sh.in@@
LINSPACE_DOWNLOAD_CACHE=${XDG_CACHE_HOME:-${HOME:?HOME is required}/.cache}/linspace
linspace_python 9 || { linspace_log ERROR 'Could not prepare Python.'; exit 1; }
"$LINSPACE_PYTHON" -I - "$@" <<'LINSPACE_STASH_PY'
@@include:src/stash/client.py@@
main('https://@@DOMAIN@@', 'clear')
LINSPACE_STASH_PY
)
main "$@"
