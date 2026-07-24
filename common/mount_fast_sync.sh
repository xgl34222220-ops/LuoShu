#!/system/bin/sh
# LuoShu fast meta-module tree synchronization.
# A foreground font switch creates many aliases that intentionally share one inode. Preserve
# those hardlinks when copying the canonical module tree into a Meta OverlayFS content mirror;
# otherwise one large CJK font can be physically copied dozens of times.
set +e

_lmfs_timeout_run() {
    _lmfs_limit="${LUOSHU_MOUNT_TIMEOUT:-45}"
    if command -v timeout >/dev/null 2>&1; then
        timeout "$_lmfs_limit" "$@"
    elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        toybox timeout "$_lmfs_limit" "$@"
    else
        "$@"
    fi
}

# Override mount_compat.sh after it has defined the original routine. Source and destination are
# normally both below /data, so cp -al can create a directory tree whose regular files share the
# original inodes. Cross-device or unsupported implementations safely fall back to bounded copies.
luoshu_copy_tree_bounded() {
    _lmfs_src="$1"
    _lmfs_dst="$2"
    [ -d "$_lmfs_src" ] || return 1
    rm -rf "$_lmfs_dst" 2>/dev/null || true

    if _lmfs_timeout_run cp -al "$_lmfs_src" "$_lmfs_dst" >/dev/null 2>&1; then
        return 0
    fi
    rm -rf "$_lmfs_dst" 2>/dev/null || true
    if _lmfs_timeout_run cp -a -l "$_lmfs_src" "$_lmfs_dst" >/dev/null 2>&1; then
        return 0
    fi

    rm -rf "$_lmfs_dst" 2>/dev/null || true
    if _lmfs_timeout_run cp -af "$_lmfs_src" "$_lmfs_dst" >/dev/null 2>&1; then
        return 0
    fi

    rm -rf "$_lmfs_dst" 2>/dev/null || true
    mkdir -p "$_lmfs_dst" 2>/dev/null || return 1
    _lmfs_timeout_run cp -rfp "$_lmfs_src/." "$_lmfs_dst/" >/dev/null 2>&1
}
