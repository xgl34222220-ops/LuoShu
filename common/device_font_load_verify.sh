#!/system/bin/sh
# Verify the active font without confusing mount-layout differences with failure.
# Android/ROM font services may expose a different path or inode view after boot;
# exact file fingerprints are strong evidence, but never the only success signal.
set +e

_dfload_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_dfload_visible_path() {
    _dfload_rel="${1#/}"
    if [ -n "${LUOSHU_VISIBLE_ROOT:-}" ]; then
        printf '%s/%s\n' "${LUOSHU_VISIBLE_ROOT%/}" "$_dfload_rel"
    else
        printf '/%s\n' "$_dfload_rel"
    fi
}

_dfload_log() {
    _dfload_module_dir="$(_dfload_module)"
    mkdir -p "$_dfload_module_dir/logs" 2>/dev/null || true
    printf '[%s] [LOAD-VERIFY] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
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

_dfload_active_font() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_active=$(head -n1 "$_dfload_module_dir/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_dfload_active" ] || _dfload_active=default
    printf '%s\n' "$_dfload_active"
}

_dfload_state_value() {
    _dfload_file="$1"
    _dfload_key="$2"
    sed -n "s/^${_dfload_key}=//p" "$_dfload_file" 2>/dev/null | head -n1 | tr -d '\r\n'
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

# v2.3.9 compared against the public compatibility view. On KernelSU/meta-overlayfs
# that directory can be an empty or stale namespace view while the real payload lives
# under .luoshu-payload and is already mounted in PID 1. Always resolve the canonical
# private payload first.
_dfload_payload_file() {
    _dfload_rel="${1#/}"
    _dfload_module_dir="$(_dfload_module)"
    for _dfload_candidate in \
        "$_dfload_module_dir/.luoshu-payload/$_dfload_rel" \
        "$_dfload_module_dir/$_dfload_rel"; do
        if [ -f "$_dfload_candidate" ]; then
            printf '%s\n' "$_dfload_candidate"
            return 0
        fi
    done
    return 1
}

_dfload_manifest_font_count() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_manifest="$_dfload_module_dir/config/font-payload-manifest.conf"
    _dfload_count=0
    if [ -s "$_dfload_manifest" ]; then
        while IFS='|' read -r _dfload_rel _dfload_sum _dfload_bytes; do
            case "$_dfload_rel" in
                */fonts/*.ttf|*/fonts/*.otf|*/fonts/*.ttc)
                    _dfload_payload_file "$_dfload_rel" >/dev/null 2>&1 && \
                        _dfload_count=$((_dfload_count + 1))
                    ;;
            esac
        done < "$_dfload_manifest"
    fi
    if [ "$_dfload_count" -eq 0 ] 2>/dev/null; then
        _dfload_count=$(find "$_dfload_module_dir/.luoshu-payload" \
            -type f \( -name '*.ttf' -o -name '*.otf' -o -name '*.ttc' \) \
            2>/dev/null | wc -l | tr -d '[:space:]')
        case "$_dfload_count" in ''|*[!0-9]*) _dfload_count=0 ;; esac
    fi
    printf '%s\n' "$_dfload_count"
}

# Strong evidence only: every comparable visible file matches the canonical private
# payload. A mismatch is diagnostic information, not a destructive failure verdict.
_dfload_exact_visible_match() {
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
        _dfload_source=$(_dfload_payload_file "$_dfload_rel") || {
            _dfload_failed=$((_dfload_failed + 1))
            continue
        }
        _dfload_visible=$(_dfload_visible_path "$_dfload_rel")
        [ -f "$_dfload_visible" ] || {
            _dfload_failed=$((_dfload_failed + 1))
            continue
        }
        _dfload_seen=$((_dfload_seen + 1))
        _dfload_source_size=$(_dfload_size "$_dfload_source")
        _dfload_visible_size=$(_dfload_size "$_dfload_visible")
        [ -n "$_dfload_source_size" ] && [ "$_dfload_source_size" = "$_dfload_visible_size" ] || {
            _dfload_failed=$((_dfload_failed + 1))
            continue
        }
        _dfload_source_fp=$(_dfload_quick_fingerprint "$_dfload_source")
        _dfload_visible_fp=$(_dfload_quick_fingerprint "$_dfload_visible")
        [ -n "$_dfload_source_fp" ] && [ "$_dfload_source_fp" = "$_dfload_visible_fp" ] || \
            _dfload_failed=$((_dfload_failed + 1))
    done < "$_dfload_manifest"
    [ "$_dfload_seen" -gt 0 ] 2>/dev/null && [ "$_dfload_failed" -eq 0 ] 2>/dev/null
}

_dfload_mount_guard() {
    _dfload_active="$1"
    _dfload_module_dir="$(_dfload_module)"
    _dfload_mount_compat="$_dfload_module_dir/common/mount_compat.sh"
    [ -f "$_dfload_mount_compat" ] || return 1
    MODDIR="$_dfload_module_dir"
    MODULE_DIR="$_dfload_module_dir"
    . "$_dfload_mount_compat"
    type luoshu_mount_verify_active >/dev/null 2>&1 || return 1
    luoshu_mount_verify_active "$_dfload_active"
}

# Medium-strength evidence. It is intentionally accepted because KernelSU and OEM
# font services can expose a transformed path/inode view even after a successful mount.
# The old verifier treated that normal layout difference as failure and later restored
# the default font, despite the custom font already being visible on screen.
_dfload_mount_transaction_active() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_mount_state=$(_dfload_state_value "$_dfload_module_dir/config/self-mount.conf" state)
    _dfload_boot_state=$(_dfload_state_value "$_dfload_module_dir/config/font-payload-boot.conf" state)
    _dfload_font_count=$(_dfload_manifest_font_count)
    [ "$_dfload_font_count" -gt 0 ] 2>/dev/null || return 1
    case "$_dfload_mount_state:$_dfload_boot_state" in
        mounted:*|confirmed:*|*:confirmed|*:booting) return 0 ;;
        *) return 1 ;;
    esac
}

device_font_load_status() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_active=$(_dfload_active_font)
    if [ "$_dfload_active" = default ]; then
        _dfload_write_simple not-applicable default-font "$_dfload_active" system
        return 0
    fi

    _dfload_conf="$_dfload_module_dir/config/device-font-load-verification.conf"
    _dfload_verified_state=$(_dfload_state_value "$_dfload_conf" state)
    _dfload_verified_active=$(_dfload_state_value "$_dfload_conf" activeFont)
    if [ "$_dfload_verified_state" = verified ] && [ "$_dfload_verified_active" = "$_dfload_active" ]; then
        return 0
    fi

    if _dfload_mount_transaction_active; then
        _dfload_write_simple verified mount-transaction-active "$_dfload_active" mount-confirmed
        return 0
    fi

    _dfload_mount_state=$(_dfload_state_value "$_dfload_module_dir/config/self-mount.conf" state)
    if [ "$_dfload_mount_state" = failed ]; then
        _dfload_write_simple failed self-mount-failed "$_dfload_active" compatibility
        return 1
    fi

    _dfload_write_simple pending awaiting-mount-confirmation "$_dfload_active" compatibility
    return 2
}

device_font_load_verify() {
    _dfload_module_dir="$(_dfload_module)"
    _dfload_active=$(_dfload_active_font)
    if [ "$_dfload_active" = default ]; then
        _dfload_write_simple not-applicable default-font "$_dfload_active" system
        return 2
    fi

    if _dfload_exact_visible_match; then
        _dfload_write_simple verified visible-font-files-match "$_dfload_active" mount-verified
        _dfload_log "系统可见字体与私有负载完全一致：$_dfload_active"
        return 0
    fi

    if _dfload_mount_guard "$_dfload_active"; then
        _dfload_write_simple verified pid1-mount-visible "$_dfload_active" mount-verified
        _dfload_log "PID 1 主命名空间已确认字体挂载；文件布局差异仅保留为诊断信息：$_dfload_active"
        return 0
    fi

    if _dfload_mount_transaction_active; then
        _dfload_write_simple verified mount-active-visible-layout-differs "$_dfload_active" mount-confirmed
        _dfload_log "字体挂载事务有效，但系统字体服务暴露的文件布局与负载不同；不再误判失败或恢复默认字体：$_dfload_active"
        return 0
    fi

    _dfload_mount_state=$(_dfload_state_value "$_dfload_module_dir/config/self-mount.conf" state)
    if [ "$_dfload_mount_state" = failed ]; then
        _dfload_write_simple failed self-mount-failed "$_dfload_active" compatibility
        _dfload_log "字体自挂载明确失败：$_dfload_active"
        return 1
    fi

    _dfload_write_simple pending mount-evidence-pending "$_dfload_active" compatibility
    _dfload_log "暂未取得挂载证据，保留当前字体负载并等待下一次检测：$_dfload_active"
    return 2
}

if [ "${0##*/}" = device_font_load_verify.sh ]; then
    case "${1:-status}" in
        status|auto) device_font_load_status ;;
        verify|deep) device_font_load_verify ;;
        *) printf 'usage: %s {status|verify}\n' "$0" >&2; exit 2 ;;
    esac
fi
