#!/system/bin/sh
# Final policy overrides for LuoShu v2.2.7 mount compatibility.
# Direct-source engines are migration-friendly and non-invasive; real dual-directory
# metamodules retain strict marker, mountpoint and supported-partition validation.
set +e

# Keep every v2.2.7 probe injection contract working. New self-mount tests use
# LUOSHU_SELF_MOUNT_VISIBLE_ROOT, while the existing runtime/tests use the older
# LUOSHU_VISIBLE_PROBE_ROOT or a direct LUOSHU_VISIBLE_PROBE file.
_luoshu_self_visible_root() {
    printf '%s\n' "${LUOSHU_SELF_MOUNT_VISIBLE_ROOT:-${LUOSHU_VISIBLE_PROBE_ROOT:-}}"
}

_luoshu_visible_path() {
    _lmcvp_path="$1"
    if [ "$_lmcvp_path" = /system/etc/luoshu/mount-probe.conf ] && \
       [ -n "${LUOSHU_VISIBLE_PROBE:-}" ]; then
        printf '%s\n' "$LUOSHU_VISIBLE_PROBE"
        return 0
    fi
    _lmcvp_root=$(_luoshu_self_visible_root)
    if [ -n "$_lmcvp_root" ]; then
        printf '%s%s\n' "${_lmcvp_root%/}" "$_lmcvp_path"
    else
        printf '%s\n' "$_lmcvp_path"
    fi
}

# Hybrid Mount v4 uses default_mode globally and per module. The v2.2.7 base
# parser only knew older backend/mode keys, so keep reporting and diagnostics in
# sync with current Full/Lite/Nano configuration without editing Hybrid's files.
_luoshu_hybrid_mode_from_file() {
    _lhmff_file="$1"
    [ -f "$_lhmff_file" ] || return 1
    awk '
        function clean(v) {
            sub(/[[:space:]]*#.*/, "", v)
            sub(/^[^=]*=[[:space:]]*/, "", v)
            gsub(/["\047[:space:]]/, "", v)
            return tolower(v)
        }
        /^[[:space:]]*\[/ {
            section=$0
            sub(/[[:space:]]*#.*/, "", section)
            gsub(/["\047[:space:]]/, "", section)
            section=tolower(section)
            in_luoshu=(section=="[rules.luoshu]")
            next
        }
        /^[[:space:]]*default_mode[[:space:]]*=/ {
            value=clean($0)
            if (in_luoshu) module_value=value
            else if (global_value=="") global_value=value
        }
        END {
            if (module_value!="") print module_value
            else if (global_value!="") print global_value
        }
    ' "$_lhmff_file" 2>/dev/null | tail -n1
}

luoshu_hybrid_backend() {
    if [ -n "${LUOSHU_META_TEST_BACKEND:-}" ]; then
        printf '%s\n' "$LUOSHU_META_TEST_BACKEND"
        return 0
    fi

    for _lhb_file in \
        /data/adb/hybrid-mount/config.toml \
        /data/adb/metamodule/config.toml \
        /data/adb/modules/hybrid_mount/config.toml \
        /data/adb/modules/meta-hybrid_mount/config.toml \
        /data/adb/modules/hybrid-mount/config.toml; do
        _lhb_value=$(_luoshu_hybrid_mode_from_file "$_lhb_file")
        case "$_lhb_value" in
            overlay|overlayfs) printf 'overlayfs\n'; return 0 ;;
            magic|magic-mount|magic_mount) printf 'magic-mount\n'; return 0 ;;
            kasumi) printf 'kasumi\n'; return 0 ;;
        esac
    done
    printf 'unknown\n'
}

luoshu_mount_preflight() {
    _lmcp_active="${1:-unknown}"
    _lmcp_engine="${2:-$(luoshu_detect_mount_engine)}"
    LUOSHU_MOUNT_PREFLIGHT_ERROR=''

    [ ! -e "$LUOSHU_MOUNT_MODDIR/remove" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='模块存在 remove 标记'
        return 1
    }

    if _luoshu_direct_source_engine "$_lmcp_engine"; then
        # A font transaction is an explicit request to activate LuoShu. Recover only
        # LuoShu-local markers left by older failed transactions; never edit another
        # metamodule's configuration, whitelist, package directory or marker files.
        if [ "$_lmcp_active" != default ]; then
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
            rm -f \
                "$LUOSHU_MOUNT_MODDIR/skip_mount" \
                "$LUOSHU_MOUNT_MODDIR/skip_mountify" \
                "$LUOSHU_MOUNT_MODDIR/mount_error" 2>/dev/null || true
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

    _lmcp_base=$(luoshu_dual_content_base)
    luoshu_mountpoint_ready "$_lmcp_base" || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像未挂载：$_lmcp_base"
        return 1
    }
    [ -w "$_lmcp_base" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像不可写：$_lmcp_base"
        return 1
    }

    _lmcp_unsupported=''
    for _lmcp_partition in $(luoshu_used_partitions); do
        if ! luoshu_meta_partition_supported "$_lmcp_partition"; then
            _lmcp_unsupported="${_lmcp_unsupported}${_lmcp_unsupported:+,}$_lmcp_partition"
        fi
    done
    [ -z "$_lmcp_unsupported" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="双目录元模块未声明字体负载分区：$_lmcp_unsupported"
        return 1
    }
    return 0
}
