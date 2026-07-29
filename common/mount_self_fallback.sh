#!/system/bin/sh
# LuoShu v2.2.7 self-mount fallback and non-invasive direct-source compatibility.
# This file is sourced after mount_compat.sh. It never edits metamodule configuration.
set +e

_luoshu_self_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

LUOSHU_MOUNT_MODDIR="${LUOSHU_MOUNT_MODDIR:-$(_luoshu_self_module)}"

_luoshu_self_state_root() {
    printf '%s\n' "${LUOSHU_SELF_MOUNT_STATE_ROOT:-/data/adb/luoshu/self-mount}"
}

_luoshu_self_visible_root() {
    printf '%s\n' "${LUOSHU_SELF_MOUNT_VISIBLE_ROOT:-}"
}

_luoshu_self_boot_id() {
    if [ -n "${LUOSHU_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_BOOT_ID"
        return 0
    fi
    _lsbi_value=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    if [ -z "$_lsbi_value" ] && command -v getprop >/dev/null 2>&1; then
        _lsbi_value=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    fi
    [ -n "$_lsbi_value" ] || _lsbi_value=unknown
    printf '%s\n' "$_lsbi_value"
}

_luoshu_self_log() {
    _lsml_module=$(_luoshu_self_module)
    mkdir -p "$_lsml_module/logs" 2>/dev/null || true
    printf '[%s] [SELF-MOUNT] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_lsml_module/logs/self-mount.log" 2>/dev/null || true
}

_luoshu_direct_source_engine() {
    case "${1:-$(luoshu_detect_mount_engine)}" in
        meta-overlayfs|dual-dir-metamodule) return 1 ;;
        *) return 0 ;;
    esac
}

# Mountify, Magic Mount RC/RS and Hybrid Mount consume the regular module tree.
# A font switch must not rewrite their config, whitelist or partition list.
luoshu_mountify_value() { return 1; }
luoshu_mountify_module_selected() { return 0; }
luoshu_magic_mount_ensure_partitions() { return 0; }

_luoshu_mountify_present() {
    [ -d /data/adb/mountify ] && return 0
    for _lsp_path in \
        /data/adb/modules/mountify \
        /data/adb/modules/Mountify \
        /data/adb/modules/*mountify* \
        /data/adb/modules/*Mountify*; do
        [ -d "$_lsp_path" ] || continue
        [ ! -e "$_lsp_path/disable" ] && [ ! -e "$_lsp_path/remove" ] || continue
        return 0
    done
    return 1
}

_luoshu_magic_mount_present() {
    for _lsp_path in \
        /data/adb/modules/magic_mount_rc \
        /data/adb/modules/magic-mount-rc \
        /data/adb/modules/magic_mount_rs \
        /data/adb/modules/magic-mount-rs \
        /data/adb/modules/meta-mm \
        /data/adb/modules/*magic*mount* \
        /data/adb/modules/*Magic*Mount*; do
        [ -d "$_lsp_path" ] || continue
        [ ! -e "$_lsp_path/disable" ] && [ ! -e "$_lsp_path/remove" ] || continue
        return 0
    done
    [ -e /data/adb/metamodule/meta-mm ] || \
    [ -e /data/adb/metamodule/meta-mm-rs ] || \
    [ -e /data/adb/modules/meta-mm/meta-mm ] || \
    [ -e /data/adb/modules/magic_mount_rc/meta-mm ] || \
    [ -e /data/adb/modules/magic_mount_rs/meta-mm ] || \
    [ -f /data/adb/magic_mount/config.toml ]
}

# Only LuoShu-local stale markers are cleared. External metamodule state is untouched.
luoshu_mount_preflight() {
    _lsmp_active="${1:-unknown}"
    _lsmp_engine=$(luoshu_detect_mount_engine)
    LUOSHU_MOUNT_PREFLIGHT_ERROR=''

    [ ! -e "$LUOSHU_MOUNT_MODDIR/remove" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='模块存在 remove 标记'
        return 1
    }
    [ ! -e "$LUOSHU_MOUNT_MODDIR/disable" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='洛书模块已被禁用'
        return 1
    }

    if _luoshu_direct_source_engine "$_lsmp_engine"; then
        if [ "$_lsmp_active" != default ]; then
            rm -f \
                "$LUOSHU_MOUNT_MODDIR/skip_mount" \
                "$LUOSHU_MOUNT_MODDIR/skip_mountify" \
                "$LUOSHU_MOUNT_MODDIR/mount_error" 2>/dev/null || true
        fi
        return 0
    fi

    [ ! -e "$LUOSHU_MOUNT_MODDIR/skip_mount" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 skip_mount，双目录元模块不会挂载洛书'
        return 1
    }
    [ ! -e "$LUOSHU_MOUNT_MODDIR/mount_error" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR='检测到 mount_error，双目录元模块未准备完成'
        return 1
    }
    _lsmp_base=$(luoshu_dual_content_base)
    luoshu_mountpoint_ready "$_lsmp_base" || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像未挂载：$_lsmp_base"
        return 1
    }
    [ -w "$_lsmp_base" ] || {
        LUOSHU_MOUNT_PREFLIGHT_ERROR="元模块内容镜像不可写：$_lsmp_base"
        return 1
    }
}

_luoshu_write_one_probe() {
    _lswop_active="$1"
    _lswop_engine="$2"
    _lswop_partition="$3"
    _lswop_nonce="$4"
    _lswop_manifest="$5"
    _lswop_directory="$LUOSHU_MOUNT_MODDIR/$_lswop_partition/etc/luoshu"
    mkdir -p "$_lswop_directory" 2>/dev/null || return 1
    {
        printf 'id=%s\n' "$(luoshu_module_id)"
        printf 'font=%s\n' "$_lswop_active"
        printf 'engine=%s\n' "$_lswop_engine"
        printf 'partition=%s\n' "$_lswop_partition"
        printf 'nonce=%s-%s\n' "$_lswop_nonce" "$_lswop_partition"
    } > "$_lswop_directory/mount-probe.conf.tmp.$$" 2>/dev/null || return 1
    mv -f "$_lswop_directory/mount-probe.conf.tmp.$$" \
        "$_lswop_directory/mount-probe.conf" 2>/dev/null || return 1
    chmod 0644 "$_lswop_directory/mount-probe.conf" 2>/dev/null || true
    printf '%s|%s-%s|%s\n' \
        "$_lswop_partition" "$_lswop_nonce" "$_lswop_partition" \
        "$(_luoshu_probe_path "$_lswop_partition")" >> "$_lswop_manifest"
}

# Direct-source engines and the self-mount fallback use one stable /system probe.
# Real dual-directory overlay engines keep strict per-partition probes.
luoshu_write_mount_probes() {
    _lswmp_active="${1:-unknown}"
    _lswmp_engine="${2:-$(luoshu_detect_mount_engine)}"
    _lswmp_nonce="$(_luoshu_now)-$$"
    _lswmp_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    _lswmp_temp="$_lswmp_manifest.tmp.$$"
    _lswmp_count=0

    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || return 1
    : > "$_lswmp_temp" 2>/dev/null || return 1

    if _luoshu_direct_source_engine "$_lswmp_engine"; then
        _luoshu_write_one_probe "$_lswmp_active" "$_lswmp_engine" system \
            "$_lswmp_nonce" "$_lswmp_temp" || return 1
        _lswmp_count=1
    else
        for _lswmp_partition in $(luoshu_used_partitions); do
            luoshu_meta_partition_supported "$_lswmp_partition" || continue
            _luoshu_write_one_probe "$_lswmp_active" "$_lswmp_engine" \
                "$_lswmp_partition" "$_lswmp_nonce" "$_lswmp_temp" || return 1
            _lswmp_count=$((_lswmp_count + 1))
        done
    fi

    [ "$_lswmp_count" -gt 0 ] || {
        rm -f "$_lswmp_temp" 2>/dev/null || true
        return 1
    }
    mv -f "$_lswmp_temp" "$_lswmp_manifest" 2>/dev/null || return 1
    chmod 0644 "$_lswmp_manifest" 2>/dev/null || true
    cp -f "$LUOSHU_MOUNT_MODDIR/system/etc/luoshu/mount-probe.conf" \
        "$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf" 2>/dev/null || true
}

luoshu_write_mount_probe() {
    luoshu_write_mount_probes "$@"
}

_luoshu_expected_system_nonce() {
    sed -n 's/^system|\([^|]*\)|.*/\1/p' \
        "$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf" 2>/dev/null | head -n1
}

_luoshu_visible_path() {
    _lsvp_path="$1"
    _lsvp_root=$(_luoshu_self_visible_root)
    if [ -n "$_lsvp_root" ]; then
        printf '%s%s\n' "${_lsvp_root%/}" "$_lsvp_path"
    else
        printf '%s\n' "$_lsvp_path"
    fi
}

_luoshu_system_probe_visible() {
    _lsspv_expected=$(_luoshu_expected_system_nonce)
    [ -n "$_lsspv_expected" ] || return 1
    _lsspv_probe=$(_luoshu_visible_path /system/etc/luoshu/mount-probe.conf)
    _lsspv_seen=$(sed -n 's/^nonce=//p' "$_lsspv_probe" 2>/dev/null | head -n1)
    _lsspv_partition=$(sed -n 's/^partition=//p' "$_lsspv_probe" 2>/dev/null | head -n1)
    [ "$_lsspv_expected" = "$_lsspv_seen" ] && [ "$_lsspv_partition" = system ]
}

_luoshu_self_state_value() {
    _lssv_key="$1"
    _lssv_module=$(_luoshu_self_module)
    sed -n "s/^${_lssv_key}=//p" "$_lssv_module/config/self-mount.conf" 2>/dev/null | head -n1
}

# Direct engines are verified by a real system probe or by the self-mount state.
# A missing synthetic OEM probe must never roll back an otherwise valid font payload.
luoshu_mount_verify_active() {
    _lsmva_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lsmva_active" ] || _lsmva_active=default
    _lsmva_engine=$(luoshu_detect_mount_engine)

    if [ "$_lsmva_active" = default ]; then
        luoshu_mount_record verified '系统默认字体无需挂载验证' '' 0 0
        return 0
    fi

    if _luoshu_direct_source_engine "$_lsmva_engine"; then
        if _luoshu_system_probe_visible; then
            luoshu_mount_record verified '系统主分区已读取洛书真实挂载探针' '' 0 0 system system
            return 0
        fi
        _lsmva_state=$(_luoshu_self_state_value state)
        case "$_lsmva_state" in
            mounted|degraded)
                luoshu_mount_record verified \
                    '洛书自挂载兜底已接管；最终字体状态由真实字体加载验证器确认' \
                    '' 0 0 system system
                return 0
                ;;
        esac
        luoshu_mount_record unverified '系统主分区未读取洛书挂载探针' '' 0 1 system '' system
        return 1
    fi

    _lsmva_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    [ -s "$_lsmva_manifest" ] || {
        luoshu_mount_record unverified '缺少双目录元模块分区挂载探针清单' '' 0 1 '' '' manifest
        return 1
    }
    _lsmva_partitions=''
    _lsmva_verified=''
    _lsmva_failed=''
    _lsmva_failed_count=0
    while IFS='|' read -r _lsmva_partition _lsmva_expected _lsmva_visible_path; do
        [ -n "$_lsmva_partition" ] || continue
        _lsmva_partitions="${_lsmva_partitions}${_lsmva_partitions:+,}$_lsmva_partition"
        _lsmva_visible=$(_luoshu_visible_path "$_lsmva_visible_path")
        _lsmva_seen=$(sed -n 's/^nonce=//p' "$_lsmva_visible" 2>/dev/null | head -n1)
        _lsmva_seen_partition=$(sed -n 's/^partition=//p' "$_lsmva_visible" 2>/dev/null | head -n1)
        if [ "$_lsmva_expected" = "$_lsmva_seen" ] && \
           [ "$_lsmva_partition" = "$_lsmva_seen_partition" ]; then
            _lsmva_verified="${_lsmva_verified}${_lsmva_verified:+,}$_lsmva_partition"
        else
            _lsmva_failed="${_lsmva_failed}${_lsmva_failed:+,}$_lsmva_partition"
            _lsmva_failed_count=$((_lsmva_failed_count + 1))
        fi
    done < "$_lsmva_manifest"
    if [ "$_lsmva_failed_count" -eq 0 ]; then
        luoshu_mount_record verified '双目录元模块所有字体负载分区均已读取' \
            '' 0 0 "$_lsmva_partitions" "$_lsmva_verified"
        return 0
    fi
    luoshu_mount_record unverified "部分字体分区未挂载：$_lsmva_failed" \
        '' 0 "$_lsmva_failed_count" "$_lsmva_partitions" "$_lsmva_verified" "$_lsmva_failed"
    return 1
}

_luoshu_mount_cmd() {
    if [ -n "${LUOSHU_SELF_MOUNT_COMMAND:-}" ]; then
        "$LUOSHU_SELF_MOUNT_COMMAND" "$@"
    elif command -v mount >/dev/null 2>&1; then
        mount "$@"
    elif command -v toybox >/dev/null 2>&1; then
        toybox mount "$@"
    elif [ -x /data/adb/magisk/busybox ]; then
        /data/adb/magisk/busybox mount "$@"
    elif command -v busybox >/dev/null 2>&1; then
        busybox mount "$@"
    else
        return 127
    fi
}

_luoshu_umount_cmd() {
    if [ -n "${LUOSHU_SELF_UMOUNT_COMMAND:-}" ]; then
        "$LUOSHU_SELF_UMOUNT_COMMAND" "$@"
    elif command -v umount >/dev/null 2>&1; then
        umount "$@"
    elif command -v toybox >/dev/null 2>&1; then
        toybox umount "$@"
    elif [ -x /data/adb/magisk/busybox ]; then
        /data/adb/magisk/busybox umount "$@"
    elif command -v busybox >/dev/null 2>&1; then
        busybox umount "$@"
    else
        return 127
    fi
}

_luoshu_partition_root() {
    _lspr_partition="$1"
    _lspr_visible=$(_luoshu_self_visible_root)
    if [ -n "$_lspr_visible" ]; then
        case "$_lspr_partition" in
            system) printf '%s/system\n' "${_lspr_visible%/}" ;;
            *) printf '%s/%s\n' "${_lspr_visible%/}" "$_lspr_partition" ;;
        esac
        return 0
    fi
    case "$_lspr_partition" in
        system) printf '/system\n' ;;
        *)
            if [ -d "/$_lspr_partition" ]; then
                printf '/%s\n' "$_lspr_partition"
            elif [ -d "/system/$_lspr_partition" ]; then
                printf '/system/%s\n' "$_lspr_partition"
            else
                return 1
            fi
            ;;
    esac
}

_luoshu_overlay_mount_dir() {
    _lsom_upper="$1"
    _lsom_target="$2"
    _lsom_key="$3"
    _lsom_state=$(_luoshu_self_state_root)
    _lsom_lower="$_lsom_state/lower/$_lsom_key"
    _lsom_work="$_lsom_state/work/$_lsom_key"

    [ -d "$_lsom_upper" ] && [ -d "$_lsom_target" ] || return 1
    _luoshu_umount_cmd "$_lsom_lower" >/dev/null 2>&1 || true
    rm -rf "$_lsom_lower" "$_lsom_work" 2>/dev/null || true
    mkdir -p "$_lsom_lower" "$_lsom_work" 2>/dev/null || return 1
    _luoshu_mount_cmd -o bind "$_lsom_target" "$_lsom_lower" >/dev/null 2>&1 || return 1
    if _luoshu_mount_cmd -t overlay overlay \
        -o "lowerdir=$_lsom_lower,upperdir=$_lsom_upper,workdir=$_lsom_work,index=off" \
        "$_lsom_target" >/dev/null 2>&1; then
        return 0
    fi
    rm -rf "$_lsom_work" 2>/dev/null || true
    mkdir -p "$_lsom_work" 2>/dev/null || true
    if _luoshu_mount_cmd -t overlay overlay \
        -o "lowerdir=$_lsom_lower,upperdir=$_lsom_upper,workdir=$_lsom_work" \
        "$_lsom_target" >/dev/null 2>&1; then
        return 0
    fi
    _luoshu_umount_cmd "$_lsom_lower" >/dev/null 2>&1 || true
    return 1
}

_luoshu_bind_existing_fonts() {
    _lsbef_upper="$1"
    _lsbef_target="$2"
    _lsbef_list="$3"
    _lsbef_count=0
    [ -d "$_lsbef_upper" ] && [ -d "$_lsbef_target" ] || return 1
    : > "$_lsbef_list" 2>/dev/null || return 1
    find "$_lsbef_upper" -type f 2>/dev/null | while IFS= read -r _lsbef_src; do
        _lsbef_rel=${_lsbef_src#$_lsbef_upper/}
        _lsbef_dst="$_lsbef_target/$_lsbef_rel"
        [ -f "$_lsbef_dst" ] || continue
        if _luoshu_mount_cmd -o bind "$_lsbef_src" "$_lsbef_dst" >/dev/null 2>&1; then
            printf '%s\n' "$_lsbef_dst" >> "$_lsbef_list"
        fi
    done
    _lsbef_count=$(wc -l < "$_lsbef_list" 2>/dev/null | tr -d '[:space:]')
    case "$_lsbef_count" in ''|*[!0-9]*) _lsbef_count=0 ;; esac
    [ "$_lsbef_count" -gt 0 ]
}

_luoshu_self_state_write() {
    _lssw_state="$1"
    _lssw_backend="$2"
    _lssw_mounted="$3"
    _lssw_failed="$4"
    _lssw_module=$(_luoshu_self_module)
    mkdir -p "$_lssw_module/config" 2>/dev/null || true
    {
        printf 'state=%s\n' "$_lssw_state"
        printf 'backend=%s\n' "$_lssw_backend"
        printf 'mounted=%s\n' "$_lssw_mounted"
        printf 'failed=%s\n' "$_lssw_failed"
        printf 'bootId=%s\n' "$(_luoshu_self_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lssw_module/config/self-mount.conf.tmp.$$" 2>/dev/null && \
        mv -f "$_lssw_module/config/self-mount.conf.tmp.$$" \
            "$_lssw_module/config/self-mount.conf" 2>/dev/null || true
}

# Called from post-mount.sh, after KernelSU's selected metamodule has already run.
# Existing successful mounts win. Self-mount is only the fail-open fallback.
luoshu_self_mount_ensure() {
    _lsme_module=$(_luoshu_self_module)
    _lsme_active=$(head -n1 "$_lsme_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lsme_active" ] || _lsme_active=default

    rm -f "$_lsme_module/skip_mount" "$_lsme_module/skip_mountify" \
        "$_lsme_module/mount_error" 2>/dev/null || true

    if [ "$_lsme_active" = default ]; then
        _luoshu_self_state_write idle none '' ''
        return 0
    fi

    if _luoshu_system_probe_visible; then
        _luoshu_self_state_write mounted external-mount system ''
        _luoshu_self_log '元模块或 Root 管理器已成功挂载，洛书不重复接管'
        return 0
    fi

    _lsme_mounted=''
    _lsme_failed=''
    _lsme_overlay_count=0
    _lsme_bind_count=0
    _lsme_system_fonts_ok=0
    _lsme_state_root=$(_luoshu_self_state_root)
    _lsme_bind_list="$_lsme_state_root/binds.$$"
    _lsme_mount_list="$_lsme_state_root/mounts.list"
    mkdir -p "$_lsme_state_root" 2>/dev/null || true
    : > "$_lsme_mount_list" 2>/dev/null || true

    for _lsme_partition in $(luoshu_payload_partitions); do
        _lsme_root=$(_luoshu_partition_root "$_lsme_partition") || continue
        for _lsme_subdir in fonts etc; do
            _lsme_upper="$_lsme_module/$_lsme_partition/$_lsme_subdir"
            _lsme_target="$_lsme_root/$_lsme_subdir"
            [ -d "$_lsme_upper" ] && find "$_lsme_upper" -type f -print -quit 2>/dev/null | grep -q . || continue
            if _luoshu_overlay_mount_dir "$_lsme_upper" "$_lsme_target" \
                "${_lsme_partition}-${_lsme_subdir}"; then
                _lsme_overlay_count=$((_lsme_overlay_count + 1))
                _lsme_mounted="${_lsme_mounted}${_lsme_mounted:+,}${_lsme_partition}/${_lsme_subdir}"
                printf '%s\n' "$_lsme_target" >> "$_lsme_mount_list" 2>/dev/null || true
                [ "$_lsme_partition/$_lsme_subdir" = system/fonts ] && _lsme_system_fonts_ok=1
                continue
            fi
            if [ "$_lsme_subdir" = fonts ] && \
               _luoshu_bind_existing_fonts "$_lsme_upper" "$_lsme_target" "$_lsme_bind_list"; then
                _lsme_bind_count=$((_lsme_bind_count + 1))
                cat "$_lsme_bind_list" >> "$_lsme_mount_list" 2>/dev/null || true
                _lsme_mounted="${_lsme_mounted}${_lsme_mounted:+,}${_lsme_partition}/${_lsme_subdir}:bind"
                [ "$_lsme_partition/$_lsme_subdir" = system/fonts ] && _lsme_system_fonts_ok=1
            else
                _lsme_failed="${_lsme_failed}${_lsme_failed:+,}${_lsme_partition}/${_lsme_subdir}"
            fi
        done
    done
    rm -f "$_lsme_bind_list" 2>/dev/null || true

    if [ "$_lsme_system_fonts_ok" -ne 1 ]; then
        _luoshu_self_state_write failed none "$_lsme_mounted" "${_lsme_failed:-system/fonts}"
        _luoshu_self_log "自挂载失败：system/fonts 未接管；failed=$_lsme_failed"
        return 1
    fi

    if [ -z "$_lsme_failed" ] && [ "$_lsme_bind_count" -eq 0 ]; then
        _luoshu_self_state_write mounted self-overlay "$_lsme_mounted" ''
        _luoshu_self_log "OverlayFS 自挂载成功：$_lsme_mounted"
    else
        _luoshu_self_state_write degraded self-overlay-bind "$_lsme_mounted" "$_lsme_failed"
        _luoshu_self_log "自挂载已降级接管：mounted=$_lsme_mounted failed=$_lsme_failed"
    fi
    return 0
}
