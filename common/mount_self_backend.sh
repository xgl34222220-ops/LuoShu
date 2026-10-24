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

    # Casefold rejections already in the kernel log before this attempt are not
    # evidence about this mount; only a count that grows across it is.
    _lsomb_casefold_before=$(_luoshu_overlay_casefold_rejections)

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

    # Only reached after the kernel refused the overlay. When it refused the
    # payload lower itself (encoding/casefold F2FS), retry once with a
    # read-only ext4 loop image as that lower; otherwise, or if the retry
    # fails, fall through to the unchanged per-file bind fallback.
    if luoshu_overlay_loop_retry "$_lsomb_source" "$_lsomb_target" "$_lsomb_key" "$_lsomb_lower" \
        "$_lsomb_casefold_before"; then
        if [ -n "${_lsme_mount_list:-}" ]; then
            printf '%s\n' "$_lsomb_lower" >> "$_lsme_mount_list" 2>/dev/null || true
        fi
        return 0
    fi

    _luoshu_umount_cmd "$_lsomb_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsomb_lower" 2>/dev/null || true
    return 1
}

# Number of OverlayFS casefold lower rejections currently in the kernel log.
# Prints 0 when the log cannot be read, so an unreadable log never triggers
# the loop fallback.
_luoshu_overlay_casefold_rejections() {
    [ "${LUOSHU_OVERLAY_LOOP_DISABLE:-0}" != 1 ] || { printf '0\n'; return 0; }
    if [ -n "${LUOSHU_OVERLAY_DMESG_FILE:-}" ]; then
        cat "$LUOSHU_OVERLAY_DMESG_FILE" 2>/dev/null
    else
        dmesg 2>/dev/null
    fi | awk 'tolower($0) ~ /overlayfs:.*case-insensitive.*not supported/ { n++ } END { print n + 0 }'
}

# Casefold fallback entry: retry SOURCE on TARGET with a read-only ext4 loop
# lower, but only when the overlay attempt that just failed added a new
# casefold rejection to the kernel log (BEFORE is the count taken right before
# it). Sources mount_overlay_layer.sh lazily so the normal overlay and bind
# paths never load it. Returns 1 without side effects otherwise.
luoshu_overlay_loop_retry() {
    _lsolr_source="$1"
    _lsolr_target="$2"
    _lsolr_key="$3"
    _lsolr_lower="$4"
    _lsolr_before="$5"
    [ "${LUOSHU_OVERLAY_LOOP_DISABLE:-0}" != 1 ] || return 1
    case "$_lsolr_before" in ''|*[!0-9]*) return 1 ;; esac
    _lsolr_after=$(_luoshu_overlay_casefold_rejections)
    case "$_lsolr_after" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_lsolr_after" -gt "$_lsolr_before" ] || return 1
    if ! type luoshu_overlay_prepare_ext4_layer >/dev/null 2>&1; then
        _lsolr_lib="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/mount_overlay_layer.sh"
        [ -f "$_lsolr_lib" ] || return 1
        . "$_lsolr_lib" || return 1
    fi
    type _luoshu_self_log >/dev/null 2>&1 && \
        _luoshu_self_log "内核拒绝 casefold F2FS 字体下层，尝试 ext4 loop 兼容层：$_lsolr_target"
    luoshu_overlay_prepare_ext4_layer "$_lsolr_source" "$_lsolr_target" "$_lsolr_key" || return 1
    if _luoshu_mount_cmd -t overlay KSU \
        -o "lowerdir=$LUOSHU_OVERLAY_COMPAT_SOURCE:$_lsolr_lower" \
        "$_lsolr_target" >/dev/null 2>&1; then
        type _luoshu_self_log >/dev/null 2>&1 && \
            _luoshu_self_log "OverlayFS 已通过 ext4 loop 兼容层挂载：$_lsolr_target"
        return 0
    fi
    luoshu_overlay_release_ext4_layer "$_lsolr_key"
    type _luoshu_self_log >/dev/null 2>&1 && \
        _luoshu_self_log "ext4 loop 兼容层重试仍失败，回退逐文件 bind：$_lsolr_target"
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
