#!/system/bin/sh
# LuoShu foreground switch speed hotfix.
#
# Two expensive operations used to repeat during one direct switch:
#   1. apply_font_by_rom(..., quick) already prepares/installs the device payload, then
#      font_manager calls font_config_enable_for_payload() again immediately.
#   2. HyperOS v2.8 coverage-floor discovery starts embedded Python once per XML on every switch.
#
# Keep all coverage/safety semantics, but memoize the ROM-only XML discovery by input content and
# make payload preparation idempotent for the same source inside one shell process.
set +e

_luoshu_speed_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_speed_exec_uncached() {
    _lse_module="$(_luoshu_speed_module)"
    if type _luoshu_font_config_python >/dev/null 2>&1; then
        _lse_python="$(_luoshu_font_config_python)"
    elif [ -n "${LUOSHU_PYTHON:-}" ]; then
        _lse_python="$LUOSHU_PYTHON"
    else
        _lse_python="$_lse_module/common/python/bin/luoshu-python"
    fi

    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$_lse_python" "$@"
    else
        _lse_root="$_lse_module/common/python"
        PYTHONHOME="$_lse_root" \
        PYTHONPATH="$_lse_root/lib/python3.14:$_lse_root/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lse_root/lib:$_lse_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_lse_python" "$@"
    fi
}

_luoshu_speed_cksum_key() {
    _lsk_file="$1"
    [ -f "$_lsk_file" ] || return 1
    if command -v cksum >/dev/null 2>&1; then
        set -- $(cksum "$_lsk_file" 2>/dev/null)
        case "${1:-}:${2:-}" in *[!0-9:]*|:) return 1 ;; esac
        printf '%s-%s\n' "$1" "$2"
        return 0
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        _lsk_sum=$(sha256sum "$_lsk_file" 2>/dev/null | awk '{print $1; exit}')
        [ -n "$_lsk_sum" ] || return 1
        printf '%s\n' "$_lsk_sum"
        return 0
    fi
    return 1
}

# Cache only the exact v2.8 compatibility query used by hyperos_coverage_floor.sh.
# Its output depends on the XML document plus scanner implementation, not on the selected font.
# XML files are tiny, so cksum is far cheaper than repeatedly starting embedded CPython.
_luoshu_font_config_exec() {
    _lse_module="$(_luoshu_speed_module)"
    _lse_target_tool="$_lse_module/common/font_config_targets.py"
    if [ "$#" -eq 3 ] && [ "$1" = "$_lse_target_tool" ] && [ "$2" = --input ] && [ -f "$3" ]; then
        _lse_input_key="$(_luoshu_speed_cksum_key "$3")"
        _lse_tool_key="$(_luoshu_speed_cksum_key "$1")"
        if [ -n "$_lse_input_key" ] && [ -n "$_lse_tool_key" ]; then
            _lse_cache_dir="${CONFIG_DIR:-$_lse_module/config}/font-target-v28-cache"
            _lse_cache="$_lse_cache_dir/${_lse_tool_key}_${_lse_input_key}.out"
            _lse_ok="${_lse_cache}.ok"
            if [ -f "$_lse_ok" ] && [ -f "$_lse_cache" ]; then
                cat "$_lse_cache"
                return 0
            fi

            mkdir -p "$_lse_cache_dir" 2>/dev/null || {
                _luoshu_speed_exec_uncached "$@"
                return $?
            }
            _lse_tmp="${_lse_cache}.tmp.$$"
            rm -f "$_lse_tmp" 2>/dev/null || true
            if _luoshu_speed_exec_uncached "$@" > "$_lse_tmp"; then
                mv -f "$_lse_tmp" "$_lse_cache" 2>/dev/null || {
                    cat "$_lse_tmp" 2>/dev/null
                    rm -f "$_lse_tmp" 2>/dev/null || true
                    return 0
                }
                : > "$_lse_ok" 2>/dev/null || true
                chmod 0600 "$_lse_cache" "$_lse_ok" 2>/dev/null || true
                cat "$_lse_cache"
                return 0
            fi
            _lse_rc=$?
            rm -f "$_lse_tmp" 2>/dev/null || true
            return "$_lse_rc"
        fi
    fi
    _luoshu_speed_exec_uncached "$@"
}

_luoshu_speed_payload_token() {
    _lsp_family="$1"
    _lsp_module="$(_luoshu_speed_module)"
    _lsp_store="$_lsp_module/system/fonts/.luoshu-font-store"
    _lsp_source=''
    for _lsp_candidate in \
        "$_lsp_store/mix-composite.font" \
        "$_lsp_store/regular.font" \
        "$_lsp_store/compact-regular.font"; do
        [ -f "$_lsp_candidate" ] || continue
        _lsp_source="$_lsp_candidate"
        break
    done

    if [ -n "$_lsp_source" ]; then
        if command -v stat >/dev/null 2>&1; then
            _lsp_meta=$(stat -c '%d:%i:%s:%Y' "$_lsp_source" 2>/dev/null)
        elif command -v toybox >/dev/null 2>&1; then
            _lsp_meta=$(toybox stat -c '%d:%i:%s:%Y' "$_lsp_source" 2>/dev/null)
        else
            _lsp_meta=''
        fi
        [ -n "$_lsp_meta" ] && {
            printf '%s|%s\n' "$_lsp_family" "$_lsp_meta"
            return 0
        }
    fi
    printf '%s|pid:%s\n' "$_lsp_family" "$$"
}

_luoshu_speed_remember_payload() {
    LUOSHU_SPEED_READY_TOKEN="$1"
    LUOSHU_SPEED_READY_RESULT="$2"
    LUOSHU_SPEED_READY_RC="$3"
}

# Final override of device_font_payload_bridge.sh. Function lookup is dynamic, so the bridge's
# apply_font_by_rom() automatically calls this implementation too. The second call made by
# font_manager then returns the already computed result instead of rebuilding 9 weights, Mono,
# device slots and HyperOS coverage a second time.
font_config_enable_for_payload() {
    _lsp_family="${1:-unknown}"
    _lsp_token="$(_luoshu_speed_payload_token "$_lsp_family")"
    if [ -n "${LUOSHU_SPEED_READY_TOKEN:-}" ] && [ "$LUOSHU_SPEED_READY_TOKEN" = "$_lsp_token" ]; then
        LUOSHU_DEVICE_PAYLOAD_RESULT="${LUOSHU_SPEED_READY_RESULT:-slot-only}"
        case "${LUOSHU_SPEED_READY_RC:-1}" in
            0) return 0 ;;
            *) return 1 ;;
        esac
    fi

    LUOSHU_DEVICE_PAYLOAD_RESULT='preparing'
    type font_config_prepare_payload_weights >/dev/null 2>&1 || {
        LUOSHU_DEVICE_PAYLOAD_RESULT='prepare-failed'
        return 1
    }
    font_config_prepare_payload_weights || {
        LUOSHU_DEVICE_PAYLOAD_RESULT='prepare-failed'
        type font_config_disable >/dev/null 2>&1 && font_config_disable
        return 1
    }

    if type device_font_payload_build_install >/dev/null 2>&1; then
        device_font_payload_build_install "$_lsp_family"
        _lsp_rc=$?
        case "$_lsp_rc" in
            0)
                LUOSHU_DEVICE_PAYLOAD_RESULT='device'
                _luoshu_speed_remember_payload "$_lsp_token" device 0
                return 0
                ;;
            1)
                LUOSHU_DEVICE_PAYLOAD_RESULT='device-failed'
                type font_config_disable >/dev/null 2>&1 && font_config_disable
                return 1
                ;;
            2) LUOSHU_DEVICE_PAYLOAD_RESULT='unsupported' ;;
        esac
    fi

    if type font_config_generate >/dev/null 2>&1 && font_config_generate "$_lsp_family"; then
        LUOSHU_DEVICE_PAYLOAD_RESULT='legacy'
        _luoshu_speed_remember_payload "$_lsp_token" legacy 0
        return 0
    fi

    LUOSHU_DEVICE_PAYLOAD_RESULT='slot-only'
    _luoshu_speed_remember_payload "$_lsp_token" slot-only 1
    return 1
}
