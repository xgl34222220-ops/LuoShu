#!/system/bin/sh
# Record the active font after Android boot without rescanning the complete payload.
# The expensive FontManager/hash verifier is retained only behind the explicit `verify` command.
set +e

_dfload_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
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
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_dfload_conf}.tmp.$$" 2>/dev/null || return 1
    mv -f "${_dfload_conf}.tmp.$$" "$_dfload_conf" 2>/dev/null || return 1
    chmod 0600 "$_dfload_conf" 2>/dev/null || true
    return 0
}

# The lightweight status path may reuse only a verification record produced by the
# explicit deep verifier. A stale self-mount flag or a confirmed boot transaction is
# not proof that Android's main namespace is actually reading LuoShu's font files.
device_font_load_status() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_config="$_dfload_module_dir/config"
    _dfload_active=$(head -n1 "$_dfload_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfload_active" ] || _dfload_active=default
    if [ "$_dfload_active" = default ]; then
        _dfload_write_simple not-applicable default-font "$_dfload_active" system
        return 0
    fi

    _dfload_mount_state=$(sed -n 's/^state=//p' "$_dfload_config/self-mount.conf" 2>/dev/null | head -n1)
    if [ "$_dfload_mount_state" = failed ]; then
        _dfload_write_simple failed self-mount-failed "$_dfload_active" compatibility
        _dfload_log "字体自挂载状态失败：$_dfload_active"
        return 1
    fi

    _dfload_verified_state=$(sed -n 's/^state=//p' "$_dfload_config/device-font-load-verification.conf" 2>/dev/null | head -n1)
    _dfload_verified_active=$(sed -n 's/^activeFont=//p' "$_dfload_config/device-font-load-verification.conf" 2>/dev/null | head -n1)
    if [ "$_dfload_verified_state" = verified ] && [ "$_dfload_verified_active" = "$_dfload_active" ]; then
        return 0
    fi

    _dfload_write_simple pending awaiting-visible-font-verification "$_dfload_active" compatibility
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
    _dfload_cache_id=$(sed -n 's/^cacheId=//p' "$_dfload_engine_state" 2>/dev/null | head -n1)
    if [ -n "$_dfload_cache_id" ]; then
        _dfload_root="$_dfload_module_dir/config/device-font-cache/$_dfload_cache_id"
        printf '%s|%s\n' "$_dfload_root/payload/manifest.json" "$_dfload_root/overlay/overlay-manifest.json"
    else
        printf '%s|%s\n' \
            "$_dfload_module_dir/config/device-font-payload/manifest.json" \
            "$_dfload_module_dir/config/device-font-overlay/overlay-manifest.json"
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
        _dfload_module_file="$_dfload_module_dir/$_dfload_rel"
        _dfload_visible="/$_dfload_rel"
        _dfload_status=missing
        _dfload_expected_fingerprint=''
        _dfload_actual_fingerprint=''
        _dfload_size=0
        if [ -f "$_dfload_module_file" ]; then
            _dfload_expected_fingerprint=$(_dfload_quick_fingerprint "$_dfload_module_file")
        fi
        if [ -f "$_dfload_visible" ]; then
            _dfload_size=$(_dfload_size "$_dfload_visible")
            _dfload_actual_fingerprint=$(_dfload_quick_fingerprint "$_dfload_visible")
            if [ -n "$_dfload_expected_fingerprint" ] && \
               [ "$_dfload_size" = "$_dfload_expected_size" ] && \
               [ "$_dfload_actual_fingerprint" = "$_dfload_expected_fingerprint" ]; then
                _dfload_status=ok
            else
                _dfload_status=mismatch
            fi
        fi
        printf '%s|%s|%s|%s|%s|%s\n' \
            "$_dfload_rel" "$_dfload_visible" "$_dfload_status" \
            "$_dfload_expected_fingerprint" "$_dfload_actual_fingerprint" "${_dfload_size:-0}" >> "$_dfload_output"
    done < "$_dfload_installed"
    chmod 0600 "$_dfload_output" 2>/dev/null || true
}

# Compatibility payloads do not have the device-aligned manifest. Verify the actual
# mounted font files from the transaction manifest instead of trusting self-mount.conf.
# A single missing or mismatching file means Android can still be reading the ROM font.
_dfload_compat_fonts_visible() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_manifest="$_dfload_module_dir/config/font-payload-manifest.conf"
    [ -s "$_dfload_manifest" ] || return 1
    _dfload_seen=0
    _dfload_failed=0

    while IFS='|' read -r _dfload_rel _dfload_manifest_sum _dfload_manifest_size; do
        case "$_dfload_rel" in
            */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc) ;;
            *) continue ;;
        esac
        _dfload_seen=$((_dfload_seen + 1))
        _dfload_module_file="$_dfload_module_dir/$_dfload_rel"
        _dfload_visible_file="/$_dfload_rel"
        [ -f "$_dfload_module_file" ] && [ -f "$_dfload_visible_file" ] || {
            _dfload_failed=$((_dfload_failed + 1))
            continue
        }
        _dfload_expected_size=$(_dfload_size "$_dfload_module_file")
        _dfload_actual_size=$(_dfload_size "$_dfload_visible_file")
        case "$_dfload_expected_size:$_dfload_actual_size" in *[!0-9:]*)
            _dfload_failed=$((_dfload_failed + 1))
            continue
            ;;
        esac
        [ "$_dfload_expected_size" = "$_dfload_actual_size" ] || {
            _dfload_failed=$((_dfload_failed + 1))
            continue
        }
        _dfload_expected_fp=$(_dfload_quick_fingerprint "$_dfload_module_file")
        _dfload_actual_fp=$(_dfload_quick_fingerprint "$_dfload_visible_file")
        [ -n "$_dfload_expected_fp" ] && [ "$_dfload_expected_fp" = "$_dfload_actual_fp" ] || \
            _dfload_failed=$((_dfload_failed + 1))
    done < "$_dfload_manifest"

    [ "$_dfload_seen" -gt 0 ] && [ "$_dfload_failed" -eq 0 ]
}

_dfload_write_conf_from_json() {
    _dfload_json="$1"
    _dfload_conf="$2"
    _dfload_state=$(sed -n 's/.*"state":"\([^"]*\)".*/\1/p' "$_dfload_json" 2>/dev/null | head -n1)
    _dfload_mode=$(sed -n 's/.*"mode":"\([^"]*\)".*/\1/p' "$_dfload_json" 2>/dev/null | head -n1)
    _dfload_active=$(sed -n 's/.*"activeFont":"\([^"]*\)".*/\1/p' "$_dfload_json" 2>/dev/null | head -n1)
    [ -n "$_dfload_state" ] || _dfload_state=failed
    [ -n "$_dfload_mode" ] || _dfload_mode=compatibility
    {
        printf 'state=%s\n' "$_dfload_state"
        printf 'mode=%s\n' "$_dfload_mode"
        printf 'activeFont=%s\n' "$_dfload_active"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        printf 'json=%s\n' "$_dfload_json"
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

device_font_load_verify() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_config="$_dfload_module_dir/config"
    _dfload_active=$(head -n1 "$_dfload_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfload_active" ] || _dfload_active=default
    if [ "$_dfload_active" = default ]; then
        _dfload_write_simple not-applicable default-font "$_dfload_active"
        return 2
    fi

    _dfload_engine_state="$_dfload_config/device-font-engine.conf"
    if ! grep -q '^state=installed$' "$_dfload_engine_state" 2>/dev/null; then
        if _dfload_compat_fonts_visible; then
            _dfload_write_simple verified visible-font-files-match "$_dfload_active" mount-verified
            _dfload_log "兼容字体负载已通过系统主命名空间字体文件核验：$_dfload_active"
            return 0
        fi
        _dfload_write_simple failed visible-font-files-mismatch "$_dfload_active" compatibility
        _dfload_log '系统主命名空间中的字体文件与洛书负载不一致，禁止标记字体已生效'
        return 1
    fi

    if ! _dfload_mount_guard "$_dfload_active"; then
        _dfload_write_simple failed self-mount-not-visible "$_dfload_active"
        _dfload_log '自挂载未完整提交或未进入系统主命名空间，禁止标记字体已生效'
        return 1
    fi

    _dfload_paths=$(_dfload_manifest_paths)
    _dfload_payload=${_dfload_paths%%|*}
    _dfload_overlay=${_dfload_paths#*|}
    if [ ! -s "$_dfload_payload" ] || [ ! -s "$_dfload_overlay" ]; then
        _dfload_write_simple failed aligned-manifest-missing "$_dfload_active"
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
        --active-font "$_dfload_active" \
        --output "$_dfload_json" 2>> "$_dfload_module_dir/logs/device-font-load-verify.log")
    _dfload_rc=$?
    if [ -s "$_dfload_json" ]; then
        _dfload_write_conf_from_json "$_dfload_json" "$_dfload_conf" || true
    else
        _dfload_write_simple failed verifier-output-missing "$_dfload_active"
    fi
    case "$_dfload_rc" in
        0) _dfload_log "FontManager 已确认加载设备对齐字体：$_dfload_active" ;;
        2) _dfload_log "设备对齐字体未获得完整加载证据：$_dfload_result" ;;
        *) _dfload_log "设备对齐字体加载验证失败：$_dfload_result" ;;
    esac
    return "$_dfload_rc"
}

if [ "${0##*/}" = device_font_load_verify.sh ]; then
    case "${1:-status}" in
        status|auto) device_font_load_status ;;
        verify|deep) device_font_load_verify ;;
        *) printf 'usage: %s {status|verify}\n' "$0" >&2; exit 2 ;;
    esac
fi
