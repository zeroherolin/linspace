# Human-readable status goes to stderr; stdout remains available for data.
linspace_log() {
    local level=$1 color='' reset=''
    shift
    if [[ -t 2 && ${TERM:-dumb} != dumb && -z ${NO_COLOR:-} ]]; then
        case "$level" in STEP|INFO) color=$'\033[36m' ;; OK) color=$'\033[32m' ;; WARN) color=$'\033[33m' ;; ERROR) color=$'\033[31m' ;; esac
        reset=$'\033[0m'
    fi
    printf '[linspace] %s%-5s%s %s\n' "$color" "$level" "$reset" "$*" >&2 || true
}

linspace_path_hint() {
    local client=$1 bin=$2 active
    active=$(type -P "$client" 2>/dev/null || true)
    if [[ $active == "$bin/$client" ]]; then
        linspace_log OK "Ready: $client"
    else
        [[ -z $active ]] || linspace_log WARN "Another command is first in PATH: $active"
        linspace_log WARN "PATH setup required to run $client by name"
        linspace_log INFO 'Run this in your current terminal:'
        printf '  export PATH=%q:"$PATH"\n' "$bin" >&2 || true
        linspace_log INFO 'For future terminals, add that export to your shell startup file.'
        linspace_log INFO 'Examples: ~/.bashrc (Bash) or ~/.zshrc (Zsh). No startup file was modified.'
    fi
}
