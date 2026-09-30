#!/system/bin/sh
# Kernel-owned commit lease. No PID files, stale directories or inherited bypass
# tokens. FD9 belongs to this subshell and closes on every exit, including SIGKILL.
_lpc_python_lock_fd() {
    _lpc_pyroot="$_lpc_module/common/python"
    _lpc_python="$_lpc_pyroot/bin/luoshu-python"
    [ -x "$_lpc_python" ] || {
        echo '洛书：提交锁组件不可用，已停止提交' >&2
        return 2
    }
    # mksh keeps shell-private descriptors close-on-exec. Explicitly duplicate
    # the SAME open-file description onto stdin for this command only. Never
    # reopen the path: that would release the child's lock when it exits.
    PYTHONHOME="$_lpc_pyroot" \
    PYTHONPATH="$_lpc_pyroot/lib/python3.14:$_lpc_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_lpc_pyroot/lib:$_lpc_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_lpc_python" -c 'import errno, sys
try:
    import fcntl
    fcntl.flock(0, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as error:
    if error.errno in (errno.EACCES, errno.EAGAIN): sys.exit(1)
    print("LuoShu: commit lock failed: " + str(error), file=sys.stderr)
    sys.exit(2)
except ImportError:
    print("LuoShu: commit lock requires fcntl", file=sys.stderr)
    sys.exit(2)' 0<&9
}

_lpc_try_lock_fd() {
    if [ "${_lpc_python_only:-0}" != 1 ]; then
        # Toybox can return 1 for both contention and EBADF. A native error is
        # never itself proof of contention; confirm it with errno-aware fcntl.
        if command -v flock >/dev/null 2>&1; then
            flock -n 0 0<&9 2>/dev/null && return 0
        elif command -v busybox >/dev/null 2>&1 && busybox --list 2>/dev/null | grep -qx flock; then
            busybox flock -n 0 0<&9 2>/dev/null && return 0
        fi
        _lpc_python_only=1
    fi
    _lpc_python_lock_fd
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
    _lpc_python_only=0
    [ "${LUOSHU_PAYLOAD_LOCK_BACKEND:-auto}" != python ] || _lpc_python_only=1
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
