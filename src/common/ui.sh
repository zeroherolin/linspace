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
    local client=$1 bin=$2
    case ":${PATH:-}:" in
        *":$bin:"*) linspace_log OK "Ready: $client" ;;
        *)
            linspace_log WARN "PATH setup required to run $client by name"
            linspace_log INFO 'Run this in your current terminal:'
            printf '  export PATH=%q:"$PATH"\n' "$bin" >&2 || true
            linspace_log INFO 'For future terminals, add that export to your shell startup file.'
            linspace_log INFO 'Examples: ~/.bashrc (Bash) or ~/.zshrc (Zsh). No startup file was modified.' ;;
    esac
}
