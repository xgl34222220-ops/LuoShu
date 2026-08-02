#!/system/bin/sh
# Verify the active LuoShu payload after Android boot.
# A successful mount is recorded as mount-only until FontManagerService confirms
# a generated LuoShu file/family.  Hard integrity failures schedule a safe
# next-boot rollback; unconfirmed OEM dumps never trigger rollback by themselves.
set +e

_dfload_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_dfload_boot_id() {
    _dfload_value=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfload_value" ] || _dfload_value=unknown
    printf '%s\n' "$_dfload_value"
}

_dfload_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum 2>/dev/null | awk '{print $1}'
    else
        cksum 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

_dfload_size() {
    stat -c '%s' "$1" 2>/dev/null || wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
}

_dfload_quick_fingerprint() {
    _dfload_file="$1"
    [ -f "$_dfload_file" ] || return 1
    _dfload_bytes=$(_dfload_size "$_dfload_file")
    case "$_dfload_bytes" in ''|*[!0-9]*) return 1 ;; esac
    {
        printf 'bytes=%s\n' "$_dfload_bytes"
        head -c 65536 "$_dfload_file" 2>/dev/null || true
        if [ "$_dfload_bytes" -gt 65536 ] 2>/dev/null; then
            tail -c 65536 "$_dfload_file" 2>/dev/null || true
        fi
    } | _dfload_hash_stream
}

_dfload_log() {
    _dfload_module_dir="$(_dfload_module)"
    mkdir -p "$_dfload_module_dir/logs" 2>/dev/null || true
    printf '[%s] [LOAD-VERIFY] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_dfload_module_dir/logs/device-font-load-verify.log" 2>/dev/null || true
}

_dfload_read() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_dfload_write_simple() {
    _dfload_state="$1"
    _dfload_reason="$2"
    _dfload_active="$3"
    _dfload_mode="${4:-compatibility}"
    _dfload_module_dir="$(_dfload_module)"
    _dfload_conf="$_dfload_module_dir/config/device-font-load-verification.conf"
    mkdir -p "${_dfload_conf%/*}" 2>/dev/null || return 1
    {
        printf 'state=%s\n' "$_dfload_state"
        printf 'mode=%s\n' "$_dfload_mode"
        printf 'activeFont=%s\n' "$_dfload_active"
        printf 'reason=%s\n' "$_dfload_reason"
        printf 'bootId=%s\n' "$(_dfload_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_dfload_conf}.tmp.$$" 2>/dev/null || return 1
    mv -f "${_dfload_conf}.tmp.$$" "$_dfload_conf" 2>/dev/null || return 1
    chmod 0600 "$_dfload_conf" 2>/dev/null || true
    return 0
}

_dfload_active() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_value=$(head -n1 "$_dfload_module_dir/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfload_value" ] || _dfload_value=default
    printf '%s\n' "$_dfload_value"
}

# Read-only status: never upgrades a mounted transaction to verified.
device_font_load_status() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_active_font=$(_dfload_active)
    if [ "$_dfload_active_font" = default ]; then
        _dfload_write_simple not-applicable default-font "$_dfload_active_font" system
        return 0
    fi

    _dfload_conf="$_dfload_module_dir/config/device-font-load-verification.conf"
    _dfload_saved_active=$(_dfload_read "$_dfload_conf" activeFont)
    _dfload_saved_boot=$(_dfload_read "$_dfload_conf" bootId)
    _dfload_current_boot=$(_dfload_boot_id)
    if [ "$_dfload_saved_active" = "$_dfload_active_font" ] && \
       [ "$_dfload_saved_boot" = "$_dfload_current_boot" ]; then
        case "$(_dfload_read "$_dfload_conf" state)" in
            verified|not-applicable) return 0 ;;
            failed) return 1 ;;
            *) return 2 ;;
        esac
    fi

    _dfload_mount_state=$(_dfload_read "$_dfload_module_dir/config/self-mount.conf" state)
    _dfload_boot_state=$(_dfload_read "$_dfload_module_dir/config/font-payload-boot.conf" state)
    if [ "$_dfload_mount_state" = failed ]; then
        _dfload_write_simple failed self-mount-failed "$_dfload_active_font" compatibility
        return 1
    fi
    case "$_dfload_mount_state:$_dfload_boot_state" in
        mounted:*|*:confirmed)
            _dfload_write_simple unverified visible-mounts-do-not-prove-font-selection \
                "$_dfload_active_font" mount-only
            return 2
            ;;
    esac
    _dfload_write_simple pending awaiting-boot-transaction "$_dfload_active_font" compatibility
    return 2
}

_dfload_python() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_python_bin="$_dfload_module_dir/common/python/bin/luoshu-python"
    _dfload_engine="$_dfload_module_dir/common/device_font_load_verify.py"
    [ -x "$_dfload_python_bin" ] && [ -f "$_dfload_engine" ] || return 1
    _dfload_python_root="$_dfload_module_dir/common/python"
    PYTHONHOME="$_dfload_python_root" \
    PYTHONPATH="$_dfload_module_dir/common:$_dfload_python_root/lib/python3.14:$_dfload_python_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_dfload_python_root/lib:$_dfload_python_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_dfload_python_bin" "$_dfload_engine" "$@"
}

_dfload_dump_font_manager() {
    _dfload_output="$1"
    rm -f "$_dfload_output" 2>/dev/null || true
    if command -v cmd >/dev/null 2>&1; then
        cmd font dump > "$_dfload_output" 2>&1 || true
        if [ ! -s "$_dfload_output" ] || grep -Eqi '(^|[[:space:]])(unknown|usage:|error:)' "$_dfload_output" 2>/dev/null; then
            cmd font system > "$_dfload_output" 2>&1 || true
        fi
    fi
    if [ ! -s "$_dfload_output" ] && command -v dumpsys >/dev/null 2>&1; then
        dumpsys font > "$_dfload_output" 2>&1 || true
    fi
    chmod 0600 "$_dfload_output" 2>/dev/null || true
}

_dfload_manifest_paths() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_engine_state="$_dfload_module_dir/config/device-font-engine.conf"
    _dfload_cache_id=$(_dfload_read "$_dfload_engine_state" cacheId)
    if [ -n "$_dfload_cache_id" ]; then
        _dfload_root="$_dfload_module_dir/config/device-font-cache/$_dfload_cache_id"
        printf '%s|%s\n' "$_dfload_root/payload/manifest.json" "$_dfload_root/overlay/overlay-manifest.json"
    else
        printf '%s|%s\n' \
            "$_dfload_module_dir/config/device-font-payload/manifest.json" \
            "$_dfload_module_dir/config/device-font-overlay/overlay-manifest.json"
    fi
}

_dfload_module_source() {
    _dfload_relative="$1"
    _dfload_module_dir="$(_dfload_module)"
    for _dfload_candidate in \
        "$_dfload_module_dir/$_dfload_relative" \
        "$_dfload_module_dir/.luoshu-payload/$_dfload_relative"; do
        [ -f "$_dfload_candidate" ] && {
            printf '%s\n' "$_dfload_candidate"
            return 0
        }
    done
    return 1
}

_dfload_visible_source() {
    _dfload_relative="$1"
    if [ -f "/proc/1/root/$_dfload_relative" ]; then
        printf '/proc/1/root/%s\n' "$_dfload_relative"
    else
        printf '/%s\n' "$_dfload_relative"
    fi
}

_dfload_mount_evidence() {
    _dfload_output="$1"
    _dfload_module_dir="$(_dfload_module)"
    _dfload_installed="$_dfload_module_dir/config/device-font-installed.conf"
    : > "$_dfload_output" 2>/dev/null || return 1
    [ -s "$_dfload_installed" ] || return 0
    while IFS='|' read -r _dfload_kind _dfload_rel _dfload_manifest_hash _dfload_expected_size; do
        [ "$_dfload_kind" = file ] || continue
        case "$_dfload_rel" in */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc) ;; *) continue ;; esac
        _dfload_module_file=$(_dfload_module_source "$_dfload_rel")
        _dfload_visible=$(_dfload_visible_source "$_dfload_rel")
        _dfload_status=missing
        _dfload_expected_fingerprint=''
        _dfload_actual_fingerprint=''
        _dfload_size_value=0
        if [ -f "$_dfload_module_file" ]; then
            _dfload_expected_fingerprint=$(_dfload_quick_fingerprint "$_dfload_module_file")
        fi
        if [ -f "$_dfload_visible" ]; then
            _dfload_size_value=$(_dfload_size "$_dfload_visible")
            _dfload_actual_fingerprint=$(_dfload_quick_fingerprint "$_dfload_visible")
            if [ -n "$_dfload_expected_fingerprint" ] && \
               [ "$_dfload_size_value" = "$_dfload_expected_size" ] && \
               [ "$_dfload_actual_fingerprint" = "$_dfload_expected_fingerprint" ]; then
                _dfload_status=ok
            else
                _dfload_status=mismatch
            fi
        fi
        printf '%s|%s|%s|%s|%s|%s\n' \
            "$_dfload_rel" "$_dfload_visible" "$_dfload_status" \
            "$_dfload_expected_fingerprint" "$_dfload_actual_fingerprint" "${_dfload_size_value:-0}" >> "$_dfload_output"
    done < "$_dfload_installed"
    chmod 0600 "$_dfload_output" 2>/dev/null || true
}

_dfload_write_conf_from_json() {
    _dfload_json_file="$1"
    _dfload_conf="$2"
    _dfload_json=$(cat "$_dfload_json_file" 2>/dev/null)
    _dfload_state=$(printf '%s' "$_dfload_json" | sed -n 's/.*"state":"\([^"]*\)".*/\1/p' | head -n1)
    _dfload_mode=$(printf '%s' "$_dfload_json" | sed -n 's/.*"mode":"\([^"]*\)".*/\1/p' | head -n1)
    _dfload_active_font=$(printf '%s' "$_dfload_json" | sed -n 's/.*"activeFont":"\([^"]*\)".*/\1/p' | head -n1)
    _dfload_reason=$(printf '%s' "$_dfload_json" | sed -n 's/.*"reasons":\["\([^"]*\)".*/\1/p' | head -n1)
    [ -n "$_dfload_state" ] || _dfload_state=failed
    [ -n "$_dfload_mode" ] || _dfload_mode=compatibility
    [ -n "$_dfload_reason" ] || _dfload_reason=verification-result-unclassified
    {
        printf 'state=%s\n' "$_dfload_state"
        printf 'mode=%s\n' "$_dfload_mode"
        printf 'activeFont=%s\n' "$_dfload_active_font"
        printf 'reason=%s\n' "$_dfload_reason"
        printf 'bootId=%s\n' "$(_dfload_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        printf 'json=%s\n' "$(printf '%s' "$_dfload_json" | tr '\n\r' '  ')"
    } > "${_dfload_conf}.tmp.$$" 2>/dev/null || return 1
    mv -f "${_dfload_conf}.tmp.$$" "$_dfload_conf" 2>/dev/null || return 1
    chmod 0600 "$_dfload_conf" 2>/dev/null || true
}

_dfload_mount_guard() {
    _dfload_guard_active="$1"
    _dfload_guard_module="$(_dfload_module)"
    _dfload_guard_compat="$_dfload_guard_module/common/mount_compat.sh"
    [ -f "$_dfload_guard_compat" ] || return 1
    MODDIR="$_dfload_guard_module"
    MODULE_DIR="$_dfload_guard_module"
    . "$_dfload_guard_compat"
    type luoshu_mount_verify_active >/dev/null 2>&1 || return 1
    luoshu_mount_verify_active "$_dfload_guard_active"
}

_dfload_schedule_rollback() {
    _dfload_reason="$1"
    _dfload_active_font="$2"
    case "$_dfload_reason" in
        visible-mount-evidence-missing|visible-font-hash-mismatch|runtime-global-face-incomplete|dynamic-family-not-loaded|self-mount-not-visible|self-mount-failed) ;;
        *) return 0 ;;
    esac
    _dfload_module_dir="$(_dfload_module)"
    _dfload_flag="$_dfload_module_dir/config/font-activation-rollback.conf"
    {
        printf 'state=pending\n'
        printf 'font=%s\n' "$_dfload_active_font"
        printf 'reason=%s\n' "$_dfload_reason"
        printf 'bootId=%s\n' "$(_dfload_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_dfload_flag}.tmp.$$" 2>/dev/null && \
        mv -f "${_dfload_flag}.tmp.$$" "$_dfload_flag" 2>/dev/null || true
    chmod 0600 "$_dfload_flag" 2>/dev/null || true
    _dfload_log "检测到硬故障，已安排下次开机恢复系统默认字体：$_dfload_reason"
}

device_font_load_verify() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_config="$_dfload_module_dir/config"
    _dfload_active_font=$(_dfload_active)
    if [ "$_dfload_active_font" = default ]; then
        _dfload_write_simple not-applicable default-font "$_dfload_active_font" system
        return 0
    fi
    if ! _dfload_mount_guard "$_dfload_active_font"; then
        _dfload_write_simple failed self-mount-not-visible "$_dfload_active_font" compatibility
        _dfload_schedule_rollback self-mount-not-visible "$_dfload_active_font"
        _dfload_log '自挂载未完整提交或未进入系统主命名空间，禁止标记字体已生效'
        return 1
    fi

    _dfload_engine_state="$_dfload_config/device-font-engine.conf"
    if ! grep -q '^state=installed$' "$_dfload_engine_state" 2>/dev/null; then
        _dfload_write_simple unverified aligned-manifest-unavailable "$_dfload_active_font" mount-only
        _dfload_log "兼容字体负载挂载可见，但没有 FontManager 对齐清单：$_dfload_active_font"
        return 2
    fi

    _dfload_paths=$(_dfload_manifest_paths)
    _dfload_payload=${_dfload_paths%%|*}
    _dfload_overlay=${_dfload_paths#*|}
    if [ ! -s "$_dfload_payload" ] || [ ! -s "$_dfload_overlay" ]; then
        _dfload_write_simple failed aligned-manifest-missing "$_dfload_active_font" compatibility
        _dfload_schedule_rollback visible-mount-evidence-missing "$_dfload_active_font"
        _dfload_log '设备对齐清单缺失，禁止标记已生效'
        return 1
    fi

    _dfload_dump="$_dfload_config/device-font-manager-dump.txt"
    _dfload_mounts="$_dfload_config/device-font-mount-evidence.txt"
    _dfload_json="$_dfload_config/device-font-load-verification.json"
    _dfload_conf="$_dfload_config/device-font-load-verification.conf"
    _dfload_dump_font_manager "$_dfload_dump"
    _dfload_mount_evidence "$_dfload_mounts" || true
    _dfload_result=$(_dfload_python \
        --payload "$_dfload_payload" \
        --overlay "$_dfload_overlay" \
        --font-dump "$_dfload_dump" \
        --mount-evidence "$_dfload_mounts" \
        --engine-state "$_dfload_engine_state" \
        --active-font "$_dfload_active_font" \
        --output "$_dfload_json" 2>> "$_dfload_module_dir/logs/device-font-load-verify.log")
    _dfload_rc=$?
    if [ -s "$_dfload_json" ]; then
        _dfload_write_conf_from_json "$_dfload_json" "$_dfload_conf" || true
    else
        _dfload_write_simple failed verifier-output-missing "$_dfload_active_font" compatibility
    fi
    _dfload_state=$(_dfload_read "$_dfload_conf" state)
    _dfload_reason=$(_dfload_read "$_dfload_conf" reason)
    [ "$_dfload_state" != failed ] || _dfload_schedule_rollback "$_dfload_reason" "$_dfload_active_font"
    case "$_dfload_state" in
        verified) _dfload_log "FontManager 已确认加载设备对齐字体：$_dfload_active_font" ;;
        unverified) _dfload_log "字体挂载可见但系统未提供选用证据：$_dfload_result" ;;
        *) _dfload_log "设备字体加载验证失败：$_dfload_result" ;;
    esac
    return "$_dfload_rc"
}

device_font_load_auto() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_conf="$_dfload_module_dir/config/device-font-load-verification.conf"
    _dfload_active_font=$(_dfload_active)
    _dfload_current_boot=$(_dfload_boot_id)
    if [ "$(_dfload_read "$_dfload_conf" activeFont)" = "$_dfload_active_font" ] && \
       [ "$(_dfload_read "$_dfload_conf" bootId)" = "$_dfload_current_boot" ]; then
        case "$(_dfload_read "$_dfload_conf" state)" in
            verified|not-applicable) return 0 ;;
            failed) return 1 ;;
        esac
    fi
    device_font_load_verify
}

if [ "${0##*/}" = device_font_load_verify.sh ]; then
    case "${1:-auto}" in
        status) device_font_load_status ;;
        auto) device_font_load_auto ;;
        verify|deep) device_font_load_verify ;;
        *) printf 'usage: %s {status|auto|verify}\n' "$0" >&2; exit 2 ;;
    esac
fi
