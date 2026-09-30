#!/system/bin/sh
# Kernel-owned commit lease. No PID files, stale directories or inherited bypass
# tokens. FD9 belongs to this subshell and closes on every exit, including SIGKILL.
_lpc_try_lock_fd() {
    if [ "${LUOSHU_PAYLOAD_LOCK_BACKEND:-auto}" != python ] && command -v flock >/dev/null 2>&1; then
        flock -n 9
    elif [ "${LUOSHU_PAYLOAD_LOCK_BACKEND:-auto}" != python ] && command -v busybox >/dev/null 2>&1 && busybox --list 2>/dev/null | grep -qx flock; then
        busybox flock -n 9
    else
        # flock is associated with the inherited open-file description: the
        # Python child may exit while the shell keeps the locked FD9 open.
        _lpc_pyroot="$_lpc_module/common/python"
        _lpc_python="$_lpc_pyroot/bin/luoshu-python"
        [ -x "$_lpc_python" ] || return 2
        PYTHONHOME="$_lpc_pyroot" \
        PYTHONPATH="$_lpc_pyroot/lib/python3.14:$_lpc_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lpc_pyroot/lib:$_lpc_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_lpc_python" -c 'import sys
try: import fcntl
except ImportError: sys.exit(2)
try: fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError: sys.exit(1)
except OSError: sys.exit(2)'
    fi
}

luoshu_payload_commit_run() (
    # Commit helpers deliberately cannot nest: fail immediately instead of
    # self-deadlocking or allowing parallel descendants an inherited bypass.
    [ "${_lpc_active:-0}" = 0 ] || return 1
    _lpc_active=1
    _lpc_module="$1"; shift
    mkdir -p "$_lpc_module/config" || return 1
    # Never unlink the inode: all participants must lock the same file.
    exec 9>"$_lpc_module/config/.payload-commit.flock" || return 1
    _lpc_wait=0
    while :; do
        _lpc_try_lock_fd
        _lpc_rc=$?
        [ "$_lpc_rc" -ne 0 ] || break
        [ "$_lpc_rc" -eq 1 ] || return 1
        [ "$_lpc_wait" -lt "${LUOSHU_PAYLOAD_LOCK_TIMEOUT:-120}" ] || return 1
        sleep 1; _lpc_wait=$((_lpc_wait + 1))
    done
    # Shell redirection saves its own FD until the function returns, but closes
    # it for executed children. A background child cannot keep this lease alive.
    "$@" 9>&-
)
