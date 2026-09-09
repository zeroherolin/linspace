#!/usr/bin/env bash
# Clear all eight channels of @@DOMAIN@@/stash.
# Usage: curl -fsSL https://@@DOMAIN@@/stash/clear | bash -s -- [-t TOKEN]
set -Eeuo pipefail
BASE=https://@@DOMAIN@@/stash
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
usage() { printf 'Usage: curl -fsSL %s/clear | bash -s -- [-t TOKEN]\nThe token may also come from $STASH_TOKEN or an interactive prompt.\n' "$BASE"; }
token=${STASH_TOKEN:-}
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--token) [[ $# -ge 2 ]] || fail 'Missing value after -t.'; token=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unexpected argument: $1 (put -- after bash -s so that options reach this script)." ;;
    esac
done
if [[ -z $token ]]; then
    ( : < /dev/tty ) 2> /dev/null || fail 'No token. Pass -t TOKEN, set STASH_TOKEN, or run from a terminal.'
    IFS= read -rs -p 'Stash token: ' token < /dev/tty
    printf '\n' >&2
fi
[[ $token =~ ^[0-9a-f]{48}$ ]] || fail 'Expected a 48-character hexadecimal stash token.'
# The token travels through curl's stdin config so it never appears in the process list.
code=$(curl -q -sS --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 30 \
    --config - -X POST -o /dev/null -w '%{http_code}' "$BASE/clear" \
    <<< "user = \"stash:$token\"") || fail 'The clear request failed.'
case $code in
    204) printf 'Cleared all eight channels of %s\n' "$BASE" ;;
    401) fail 'The token was rejected.' ;;
    *) fail "Unexpected HTTP status $code." ;;
esac
