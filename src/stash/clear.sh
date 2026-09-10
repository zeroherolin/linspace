#!/usr/bin/env bash
# Usage: curl -fsSL https://@@DOMAIN@@/stash/clear | bash
set -Eeuo pipefail
command -v python3 >/dev/null || { echo 'Python 3.9+ is required.' >&2; exit 1; }
python3 - "$@" <<'LINSPACE_STASH_PY'
@@include:src/stash/client.py@@
main('https://@@DOMAIN@@', 'clear')
LINSPACE_STASH_PY
