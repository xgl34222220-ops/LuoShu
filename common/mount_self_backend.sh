#!/system/bin/sh
# LuoShu self-mount backend.
# Uses the same read-only lower-layer model as KernelSU's reference meta-overlayfs:
# module content first, captured stock tree last, and source name KSU for unified cleanup.
set +e

luoshu_self_mount_stage_for_manager() {
    case "${1:-unknown}" in
        APatch|KernelSU|KernelSU*|SukiSU|SukiSU*)
            printf 'post-mount\n'
            ;;
        *)
            # Magisk does not provide a module post-mount hook. Unknown legacy
            # managers retain the existing early path for compatibility.
            printf 'post-fs-data\n'
            ;;
    esac
}

_luoshu_overlay_mount_dir() {
    _lsomb_source="$1"
    _lsomb_target="$2"
    _lsomb_key="$3"
    _lsomb_state=$(_luoshu_self_state_root)
    _lsomb_lower="$_lsomb_state/lower/$_lsomb_key"

    [ -d "$_lsomb_source" ] && [ -d "$_lsomb_target" ] || return 1
    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    mkdir -p "$_lsomb_lower" 2>/dev/null || return 1

    # Keep a stable reference to the currently visible stock/metamodule tree before
    # placing LuoShu's own layer on the same target.
    _luoshu_mount_cmd -o bind "$_lsomb_target" "$_lsomb_lower" >/dev/null 2>&1 || return 1

    # No upperdir/workdir is needed: LuoShu only needs a merged read-only boot view.
    # Changes made by the App are intentionally picked up after the requested reboot.
    if _luoshu_mount_cmd -t overlay KSU \
        -o "lowerdir=$_lsomb_source:$_lsomb_lower" \
        "$_lsomb_target" >/dev/null 2>&1; then
        # self_mount_ensure appends the visible target too. Recording the captured
        # lower first guarantees reverse-order uninstall: target, then lower bind.
        if [ -n "${_lsme_mount_list:-}" ]; then
            printf '%s\n' "$_lsomb_lower" >> "$_lsme_mount_list" 2>/dev/null || true
        fi
        return 0
    fi

    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    return 1
}

# OverlayFS is not available on every KernelSU/HyperOS combination. The atomic
# runtime then falls back to per-file bind mounts, but the stock directory must
# still remain reachable for later inventory scans and stock-metric alignment.
# Capture it before installing any file binds and detach its propagation so the
# later child mounts cannot leak back into this stock view.
_luoshu_capture_lower_dir() {
    _lscld_target="$1"
    _lscld_key="$2"
    _lscld_state=$(_luoshu_self_state_root)
    _lscld_lower="$_lscld_state/lower/$_lscld_key"

    [ -d "$_lscld_target" ] || return 1
    _luoshu_umount_cmd "$_lscld_lower" >/dev/null 2>&1 || true
    rm -rf "$_lscld_lower" 2>/dev/null || true
    mkdir -p "$_lscld_lower" 2>/dev/null || return 1
    _luoshu_mount_cmd -o bind "$_lscld_target" "$_lscld_lower" >/dev/null 2>&1 || {
        rm -rf "$_lscld_lower" 2>/dev/null || true
        return 1
    }
    _luoshu_mount_cmd --make-private "$_lscld_lower" >/dev/null 2>&1 || true
    if [ -n "${_lsme_mount_list:-}" ]; then
        printf '%s\n' "$_lscld_lower" >> "$_lsme_mount_list" 2>/dev/null || {
            _luoshu_umount_cmd "$_lscld_lower" >/dev/null 2>&1 || true
            rm -rf "$_lscld_lower" 2>/dev/null || true
            return 1
        }
    fi
    return 0
}
