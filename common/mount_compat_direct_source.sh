#!/system/bin/sh
# Compatibility-first overrides for direct-source metamodules.
#
# Mountify, Hybrid Mount and Magic Mount read the canonical module tree directly.
# Their package ids, helper paths and partition exposure differ between releases, so LuoShu must
# not turn advisory detection/probe differences into a font-transaction rollback.
set +e

_luoshu_direct_modules_root() {
    printf '%s\n' "${LUOSHU_META_TEST_MODULES_ROOT:-/data/adb/modules}"
}

_luoshu_direct_mountify_root() {
    printf '%s\n' "${LUOSHU_META_TEST_MOUNTIFY_ROOT:-/data/adb/mountify}"
}

_luoshu_direct_magic_root() {
    printf '%s\n' "${LUOSHU_META_TEST_MAGIC_ROOT:-/data/adb/magic_mount}"
}

# Mountify has shipped with both a normal module directory and a standalone /data/adb/mountify
# state directory. Accept either contract instead of requiring one exact module.prop layout.
_luoshu_mountify_present() {
    _lmds_mountify_root=$(_luoshu_direct_mountify_root)
    if [ -d "$_lmds_mountify_root" ] || [ -f "$_lmds_mountify_root/config.sh" ]; then
        return 0
    fi

    _lmds_modules_root=$(_luoshu_direct_modules_root)
    for _lmds_path in \
        "$_lmds_modules_root/mountify" \
        "$_lmds_modules_root/Mountify" \
        "$_lmds_modules_root"/*mountify* \
        "$_lmds_modules_root"/*Mountify*; do
        [ -d "$_lmds_path" ] || continue
        [ ! -e "$_lmds_path/disable" ] && [ ! -e "$_lmds_path/remove" ] || continue
        if [ -f "$_lmds_path/module.prop" ]; then
            _luoshu_module_metadata_matches "$_lmds_path" mountify && return 0
        fi
        case "${_lmds_path##*/}" in
            *mountify*|*Mountify*) return 0 ;;
        esac
    done
    return 1
}

# Magic Mount RC/RS has used meta-mm, magic_mount_rs and other package ids. Keep every known helper
# path and allow test roots so regressions can be covered without touching /data/adb.
_luoshu_magic_mount_present() {
    _lmds_modules_root=$(_luoshu_direct_modules_root)
    for _lmds_path in "$_lmds_modules_root"/*; do
        [ -d "$_lmds_path" ] || continue
        _luoshu_module_metadata_matches "$_lmds_path" \
            magic_mount magic-mount 'magic mount' id=meta-mm && return 0
    done

    _lmds_magic_root=$(_luoshu_direct_magic_root)
    [ -f "$_lmds_magic_root/config.toml" ] || return 1
    _lmds_metamodule_root="${LUOSHU_META_TEST_METAMODULE_ROOT:-/data/adb/metamodule}"
    for _lmds_helper in \
        "$_lmds_metamodule_root/meta-mm" \
        "$_lmds_metamodule_root/meta-mm-rs" \
        "$_lmds_modules_root/magic_mount_rs/meta-mm" \
        "$_lmds_modules_root/magic_mount_rc/meta-mm" \
        "$_lmds_modules_root/meta-mm/meta-mm" \
        "$_lmds_modules_root"/*magic*mount*/meta-mm \
        "$_lmds_modules_root"/*Magic*Mount*/meta-mm; do
        [ -e "$_lmds_helper" ] && return 0
    done
    return 1
}

# Preserve the executable-path fallback used by older LuoShu releases.
luoshu_detect_root_manager() {
    if [ -n "${APATCH:-}" ] || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch\n'
    elif [ -n "${KSU:-}" ] || [ -d /data/adb/ksu ]; then
        printf 'KernelSU\n'
    elif [ -n "${MAGISK_VER_CODE:-}" ] || [ -d /data/adb/magisk ] || [ -x /data/adb/magisk/magisk ]; then
        printf 'Magisk\n'
    else
        printf 'unknown\n'
    fi
}

# Mountify whitelist files differ in location and sometimes case. Only reject when a real list was
# found and LuoShu is definitely absent; an unreadable/missing list must not block a font switch.
luoshu_mountify_module_selected() {
    _lmds_id=$(luoshu_module_id)
    _lmds_mode=$(luoshu_mountify_value mountify_mounts)
    [ -n "$_lmds_mode" ] || _lmds_mode=2
    case "$_lmds_mode" in
        1|whitelist|white-list) ;;
        *) return 0 ;;
    esac

    _lmds_found_list=0
    _lmds_mountify_root=$(_luoshu_direct_mountify_root)
    _lmds_modules_root=$(_luoshu_direct_modules_root)
    for _lmds_file in \
        "$_lmds_mountify_root/modules.txt" \
        "$_lmds_modules_root/mountify/modules.txt" \
        "$_lmds_modules_root/Mountify/modules.txt"; do
        [ -f "$_lmds_file" ] || continue
        _lmds_found_list=1
        grep -Fxiq "$_lmds_id" "$_lmds_file" 2>/dev/null && return 0
        grep -Fxiq "${LUOSHU_MOUNT_MODDIR##*/}" "$_lmds_file" 2>/dev/null && return 0
    done
    [ "$_lmds_found_list" -eq 0 ] && return 0
    return 1
}

_luoshu_probe_partitions_compat() {
    _lmds_engine="$1"
    case "$_lmds_engine" in
        mountify|hybrid-mount|magic-mount|magic-mount-rs|native-module-mount)
            # Direct-source engines are intentionally validated through one stable /system probe.
            # Their OEM partition aliases and config contracts vary too much for a rollback gate.
            printf 'system\n'
            ;;
        *)
            luoshu_used_partitions
            ;;
    esac
}

# Keep strict per-partition probes for a real dual-directory content mirror, but restore the stable
# single-/system probe for engines that read /data/adb/modules/LuoShu directly.
luoshu_write_mount_probes() {
    _lmds_active="${1:-unknown}"
    _lmds_engine=$(luoshu_detect_mount_engine)
    _lmds_id=$(luoshu_module_id)
    _lmds_nonce="$(_luoshu_now)-$$"
    _lmds_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    _lmds_temp="$_lmds_manifest.tmp.$$"
    _lmds_count=0

    mkdir -p "$LUOSHU_MOUNT_MODDIR/config" 2>/dev/null || return 1
    : > "$_lmds_temp" 2>/dev/null || return 1
    for _lmds_partition in $(_luoshu_probe_partitions_compat "$_lmds_engine"); do
        _lmds_directory="$LUOSHU_MOUNT_MODDIR/$_lmds_partition/etc/luoshu"
        mkdir -p "$_lmds_directory" 2>/dev/null || return 1
        {
            printf 'id=%s\n' "$_lmds_id"
            printf 'font=%s\n' "$_lmds_active"
            printf 'engine=%s\n' "$_lmds_engine"
            printf 'partition=%s\n' "$_lmds_partition"
            printf 'nonce=%s-%s\n' "$_lmds_nonce" "$_lmds_partition"
        } > "$_lmds_directory/mount-probe.conf.tmp.$$" 2>/dev/null || return 1
        mv -f "$_lmds_directory/mount-probe.conf.tmp.$$" \
            "$_lmds_directory/mount-probe.conf" 2>/dev/null || return 1
        chmod 0644 "$_lmds_directory/mount-probe.conf" 2>/dev/null || true
        printf '%s|%s-%s|%s\n' \
            "$_lmds_partition" "$_lmds_nonce" "$_lmds_partition" \
            "$(_luoshu_probe_path "$_lmds_partition")" >> "$_lmds_temp"
        _lmds_count=$((_lmds_count + 1))
    done

    if [ "$_lmds_count" -eq 0 ]; then
        rm -f "$_lmds_temp" 2>/dev/null || true
        return 1
    fi
    mv -f "$_lmds_temp" "$_lmds_manifest" 2>/dev/null || return 1
    chmod 0644 "$_lmds_manifest" 2>/dev/null || true
    cp -f "$LUOSHU_MOUNT_MODDIR/system/etc/luoshu/mount-probe.conf" \
        "$LUOSHU_MOUNT_MODDIR/config/mount-probe-expected.conf" 2>/dev/null || true
}

luoshu_write_mount_probe() {
    luoshu_write_mount_probes "$@"
}

_luoshu_direct_probe_engine() {
    case "$1" in
        mountify|hybrid-mount|magic-mount|magic-mount-rs) return 0 ;;
        *) return 1 ;;
    esac
}

# For direct-source metamodules, a probe is diagnostic rather than a destructive rollback gate.
# Device-font load verification remains responsible for deciding whether the selected font actually
# reached Android. This prevents one missing OEM alias/probe from disabling an otherwise working module.
luoshu_mount_verify_active() {
    _lmds_active="${1:-$(head -n1 "$LUOSHU_MOUNT_MODDIR/config/active_font.conf" 2>/dev/null)}"
    [ -n "$_lmds_active" ] || _lmds_active=default
    if [ "$_lmds_active" = default ]; then
        luoshu_mount_record verified '系统默认字体无需挂载验证' '' 0 0
        return 0
    fi

    _lmds_engine=$(luoshu_detect_mount_engine)
    _lmds_manifest="$LUOSHU_MOUNT_MODDIR/config/mount-probes-expected.conf"
    if [ ! -s "$_lmds_manifest" ]; then
        if _luoshu_direct_probe_engine "$_lmds_engine"; then
            luoshu_mount_record verified \
                '兼容模式：直接源元模块缺少旧探针清单，跳过探针回滚门槛' '' 0 0
            luoshu_mount_log "兼容模式跳过探针门槛：engine=$_lmds_engine reason=manifest-missing"
            return 0
        fi
        luoshu_mount_record unverified '缺少分区挂载探针清单' '' 0 1 '' '' manifest
        return 1
    fi

    _lmds_partitions=''
    _lmds_verified=''
    _lmds_failed=''
    _lmds_failed_count=0
    _lmds_checked=0
    while IFS='|' read -r _lmds_partition _lmds_expected _lmds_visible_path; do
        [ -n "$_lmds_partition" ] || continue
        if _luoshu_direct_probe_engine "$_lmds_engine" && [ "$_lmds_partition" != system ]; then
            continue
        fi
        _lmds_checked=$((_lmds_checked + 1))
        _lmds_partitions="${_lmds_partitions}${_lmds_partitions:+,}$_lmds_partition"
        if [ -n "${LUOSHU_VISIBLE_PROBE:-}" ] && [ "$_lmds_partition" = system ]; then
            _lmds_visible="$LUOSHU_VISIBLE_PROBE"
        elif [ -n "${LUOSHU_VISIBLE_PROBE_ROOT:-}" ]; then
            _lmds_visible="${LUOSHU_VISIBLE_PROBE_ROOT%/}$_lmds_visible_path"
        else
            _lmds_visible="$_lmds_visible_path"
        fi
        _lmds_seen=$(sed -n 's/^nonce=//p' "$_lmds_visible" 2>/dev/null | head -n1)
        _lmds_seen_partition=$(sed -n 's/^partition=//p' "$_lmds_visible" 2>/dev/null | head -n1)
        if [ "$_lmds_expected" = "$_lmds_seen" ] && [ "$_lmds_partition" = "$_lmds_seen_partition" ]; then
            _lmds_verified="${_lmds_verified}${_lmds_verified:+,}$_lmds_partition"
        else
            _lmds_failed="${_lmds_failed}${_lmds_failed:+,}$_lmds_partition"
            _lmds_failed_count=$((_lmds_failed_count + 1))
        fi
    done < "$_lmds_manifest"

    if [ "$_lmds_failed_count" -eq 0 ] && [ "$_lmds_checked" -gt 0 ]; then
        luoshu_mount_record verified \
            '字体挂载探针已从系统路径读取' '' 0 0 \
            "$_lmds_partitions" "$_lmds_verified"
        return 0
    fi

    if _luoshu_direct_probe_engine "$_lmds_engine"; then
        luoshu_mount_record verified \
            "兼容模式：$_lmds_engine 未暴露系统探针，保留诊断但不触发字体回滚" \
            '' 0 0 "${_lmds_partitions:-system}" "$_lmds_verified" "$_lmds_failed"
        luoshu_mount_log \
            "兼容模式跳过探针门槛：engine=$_lmds_engine failed=${_lmds_failed:-system}"
        return 0
    fi

    luoshu_mount_record unverified \
        "部分字体分区未挂载：$_lmds_failed" '' 0 "$_lmds_failed_count" \
        "$_lmds_partitions" "$_lmds_verified" "$_lmds_failed"
    return 1
}
