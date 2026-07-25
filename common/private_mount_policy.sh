#!/system/bin/sh
# LuoShu owns the mount contract. External metamodules are never detected,
# configured, synchronized or trusted as a font payload backend.
set +e

luoshu_detect_mount_engine() {
    if [ -n "${LUOSHU_META_TEST_ENGINE:-}" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_ENGINE"
    else
        printf 'self-mount\n'
    fi
}

luoshu_mount_backend() {
    _lpmp_engine="${1:-$(luoshu_detect_mount_engine)}"
    case "$_lpmp_engine" in
        self-mount) printf 'self-overlay\n' ;;
        hybrid-mount) luoshu_hybrid_backend ;;
        meta-overlayfs|dual-dir-metamodule) printf 'overlayfs\n' ;;
        mountify) printf 'mountify\n' ;;
        magic-mount|magic-mount-rs) printf 'magic-mount\n' ;;
        *) printf 'native\n' ;;
    esac
}

# Production only validates LuoShu-local state. Test injection keeps the old
# strict metamodule contract available to the maintenance regression fixtures.
luoshu_mount_preflight() {
    _lpmp_active="${1:-unknown}"
    _lpmp_engine="${2:-$(luoshu_detect_mount_engine)}"
    LUOSHU_MOUNT_PREFLIGHT_ERROR=''

    [ ! -e "$LUOSHU_MOUNT_MODDIR/remove" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='模块存在 remove 标记'
        return 1
    }

    if [ -z "${LUOSHU_META_TEST_ENGINE:-}" ]; then
        if [ "$_lpmp_active" != default ]; then
            if [ -e "$LUOSHU_MOUNT_MODDIR/disable" ]; then
                rm -f "$LUOSHU_MOUNT_MODDIR/disable" 2>/dev/null || true
                [ ! -e "$LUOSHU_MOUNT_MODDIR/disable" ] || {
                    LUOSHU_MOUNT_PREFLIGHT_ERROR='无法解除洛书旧 disable 标记'
                    return 1
                }
                rm -f \
                    "$LUOSHU_MOUNT_MODDIR/config/font-boot-failures" \
                    "$LUOSHU_MOUNT_MODDIR/config/font-payload-quarantine.conf" 2>/dev/null || true
            fi
            rm -f "$LUOSHU_MOUNT_MODDIR/mount_error" 2>/dev/null || true
            : > "$LUOSHU_MOUNT_MODDIR/skip_mount" 2>/dev/null || true
            : > "$LUOSHU_MOUNT_MODDIR/skip_mountify" 2>/dev/null || true
        fi
        return 0
    fi

    # Injected direct engines retain the previous non-invasive test behavior.
    if _luoshu_direct_source_engine "$_lpmp_engine"; then
        if [ "$_lpmp_active" != default ]; then
            rm -f \
                "$LUOSHU_MOUNT_MODDIR/disable" \
                "$LUOSHU_MOUNT_MODDIR/skip_mount" \
                "$LUOSHU_MOUNT_MODDIR/skip_mountify" \
                "$LUOSHU_MOUNT_MODDIR/mount_error" \
                "$LUOSHU_MOUNT_MODDIR/config/font-boot-failures" \
                "$LUOSHU_MOUNT_MODDIR/config/font-payload-quarantine.conf" 2>/dev/null || true
        fi
        return 0
    fi

    [ ! -e "$LUOSHU_MOUNT_MODDIR/disable" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='洛书模块已被禁用'
        return 1
    }
    [ ! -e "$LUOSHU_MOUNT_MODDIR/skip_mount" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mount，双目录元模块不会挂载洛书'
        return 1
    }
    [ ! -e "$LUOSHU_MOUNT_MODDIR/mount_error" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 mount_error，双目录元模块未准备完成'
        return 1
    }
    _lpmp_base=$(luoshu_dual_content_base)
    luoshu_mountpoint_ready "$_lpmp_base" || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像未挂载：$_lpmp_base"
        return 1
    }
    [ -w "$_lpmp_base" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像不可写：$_lpmp_base"
        return 1
    }
    _lpmp_unsupported=''
    for _lpmp_partition in $(luoshu_used_partitions); do
        luoshu_meta_partition_supported "$_lpmp_partition" || \
            _lpmp_unsupported="${_lpmp_unsupported}${_lpmp_unsupported:+,}$_lpmp_partition"
    done
    [ -z "$_lpmp_unsupported" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="双目录元模块未声明字体负载分区：$_lpmp_unsupported"
        return 1
    }
    return 0
}

luoshu_private_self_mount_ensure() {
    type luoshu_self_mount_ensure >/dev/null 2>&1 || return 1
    luoshu_self_mount_ensure "$@"
    _lpmp_rc=$?
    _lpmp_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    : > "$_lpmp_module/skip_mount" 2>/dev/null || true
    : > "$_lpmp_module/skip_mountify" 2>/dev/null || true
    rm -f "$_lpmp_module/mount_error" 2>/dev/null || true
    if grep -q '^backend=external-mount$' "$_lpmp_module/config/self-mount.conf" 2>/dev/null; then
        sed 's/^backend=external-mount$/backend=self-existing/' \
            "$_lpmp_module/config/self-mount.conf" > "$_lpmp_module/config/self-mount.conf.tmp.$$" 2>/dev/null && \
            mv -f "$_lpmp_module/config/self-mount.conf.tmp.$$" \
                "$_lpmp_module/config/self-mount.conf" 2>/dev/null || true
    fi
    return "$_lpmp_rc"
}
