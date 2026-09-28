# Serialize Mihomo install, subscription, restart and uninstall. The lock lives in a
# root-owned directory so an unprivileged local account cannot pre-create and hold it.
LINSPACE_MIHOMO_LOCK_DIR=/run/linspace-mihomo
LINSPACE_MIHOMO_LOCK=$LINSPACE_MIHOMO_LOCK_DIR/lock
linspace_mihomo_lock() {
    [[ ! -L $LINSPACE_MIHOMO_LOCK_DIR && ! -L $LINSPACE_MIHOMO_LOCK ]] || return 1
    install -d -m 700 -o root -g root "$LINSPACE_MIHOMO_LOCK_DIR" || return 1
    [[ -O $LINSPACE_MIHOMO_LOCK_DIR ]] || return 1
    exec 9>>"$LINSPACE_MIHOMO_LOCK" || return 1
    [[ -O $LINSPACE_MIHOMO_LOCK && -f $LINSPACE_MIHOMO_LOCK ]] || return 1
    flock -n 9
}
