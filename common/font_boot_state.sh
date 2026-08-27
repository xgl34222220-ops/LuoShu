#!/system/bin/sh
# One-reboot font transaction marker and late-boot convergence helpers.
set +e

_lfbs_module() {
    printf '%s\n' "${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
}

_lfbs_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_lfbs_boot_id() {
    if [ -n "${LUOSHU_TEST_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_TEST_BOOT_ID"
        return
    fi
    if type luoshu_current_boot_id >/dev/null 2>&1; then
        luoshu_current_boot_id
        return
    fi
    _lfbs_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_lfbs_id" ] || _lfbs_id=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    [ -n "$_lfbs_id" ] || _lfbs_id=unknown
    printf '%s\n' "$_lfbs_id"
}

luoshu_text_reboot_mark() {
    _lfbs_font="${1:-default}"
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_marker="$_lfbs_module_dir/config/text_reboot_required.conf"
    _lfbs_temp="${_lfbs_marker}.tmp.$$"
    mkdir -p "${_lfbs_marker%/*}" 2>/dev/null || return 1
    {
        printf 'font=%s\n' "$_lfbs_font"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        printf 'bootId=%s\n' "$(_lfbs_boot_id)"
    } > "$_lfbs_temp" 2>/dev/null || return 1
    mv -f "$_lfbs_temp" "$_lfbs_marker" 2>/dev/null || return 1
    chmod 0644 "$_lfbs_marker" 2>/dev/null || true
}

# A successful foreground commit is newer than an update/dynamic-config migration
# marker. Recover only that narrow stale-marker case.
luoshu_font_rebuild_marker_reconcile() {
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_config="$_lfbs_module_dir/config"
    _lfbs_pending="$_lfbs_config/font-payload-rebuild-pending.conf"
    [ -s "$_lfbs_pending" ] || return 0
    _lfbs_active=$(head -n1 "$_lfbs_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    _lfbs_pending_font=$(_lfbs_value "$_lfbs_pending" font)
    _lfbs_pending_time=$(_lfbs_value "$_lfbs_pending" time)
    _lfbs_boot="$_lfbs_config/font-payload-boot.conf"
    _lfbs_boot_font=$(_lfbs_value "$_lfbs_boot" font)
    _lfbs_boot_time=$(_lfbs_value "$_lfbs_boot" time)
    _lfbs_boot_state=$(_lfbs_value "$_lfbs_boot" state)
    _lfbs_schema=$(_lfbs_value "$_lfbs_config/font-payload-schema.conf" schema)
    case "$_lfbs_pending_time:$_lfbs_boot_time" in *[!0-9:]*|:*) return 2 ;; esac
    case "$_lfbs_boot_state" in prepared|booting|confirmed) ;; *) return 2 ;; esac
    [ -n "$_lfbs_active" ] && [ "$_lfbs_active" != default ] || return 2
    [ "$_lfbs_pending_font" = "$_lfbs_active" ] && [ "$_lfbs_boot_font" = "$_lfbs_active" ] || return 2
    [ "$_lfbs_schema" = "${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-device-template-v2-baseline-v9-rolegraph-v2}" ] || return 2
    [ "$_lfbs_boot_time" -ge "$_lfbs_pending_time" ] 2>/dev/null || return 2
    [ -s "$_lfbs_config/font-payload-manifest.conf" ] || return 2
    rm -f "$_lfbs_pending" "$_lfbs_config/font-payload-reapply-notified.conf" 2>/dev/null || true
    return 0
}

_lfbs_confirm_boot_file() {
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_config="$_lfbs_module_dir/config"
    _lfbs_boot="$_lfbs_config/font-payload-boot.conf"
    _lfbs_state=$(_lfbs_value "$_lfbs_boot" state)
    [ "$_lfbs_state" = booting ] || return 0
    _lfbs_font=$(_lfbs_value "$_lfbs_boot" font)
    _lfbs_generation=$(_lfbs_value "$_lfbs_boot" generation)
    _lfbs_temp="${_lfbs_boot}.tmp.$$"
    {
        printf 'state=confirmed\n'
        printf 'font=%s\n' "${_lfbs_font:-unknown}"
        [ -z "$_lfbs_generation" ] || printf 'generation=%s\n' "$_lfbs_generation"
        printf 'bootId=%s\n' "$(_lfbs_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lfbs_temp" 2>/dev/null || return 1
    mv -f "$_lfbs_temp" "$_lfbs_boot" 2>/dev/null || return 1
    chmod 0644 "$_lfbs_boot" 2>/dev/null || true
}

luoshu_text_reboot_reconcile() {
    _lfbs_module_dir="$(_lfbs_module)"
    _lfbs_config="$_lfbs_module_dir/config"
    _lfbs_marker="$_lfbs_config/text_reboot_required.conf"
    [ -s "$_lfbs_marker" ] || return 0
    _lfbs_marker_boot=$(_lfbs_value "$_lfbs_marker" bootId)
    _lfbs_current_boot=$(_lfbs_boot_id)
    # Never clear a marker using the previous font that is still mounted in this boot.
    [ -n "$_lfbs_marker_boot" ] && [ "$_lfbs_marker_boot" = "$_lfbs_current_boot" ] && return 2

    luoshu_font_rebuild_marker_reconcile >/dev/null 2>&1 || true
    _lfbs_boot_state=$(_lfbs_value "$_lfbs_config/font-payload-boot.conf" state)
    case "$_lfbs_boot_state" in booting|confirmed) ;; *) return 2 ;; esac
    _lfbs_verify="$_lfbs_module_dir/common/device_font_load_verify.sh"
    [ -f "$_lfbs_verify" ] || return 2
    MODDIR="$_lfbs_module_dir" MODULE_DIR="$_lfbs_module_dir" sh "$_lfbs_verify" verify >/dev/null 2>&1
    _lfbs_verify_state=$(_lfbs_value "$_lfbs_config/device-font-load-verification.conf" state)
    case "$_lfbs_verify_state" in verified|not-applicable) ;; *) return 2 ;; esac
    _lfbs_confirm_boot_file || return 1
    rm -f "$_lfbs_marker" "$_lfbs_config/font-mount-verify-failures" \
        "$_lfbs_config/font-boot-inconclusive.conf" 2>/dev/null || true
    return 0
}

if [ "${0##*/}" = font_boot_state.sh ]; then
    case "${1:-reconcile}" in
        mark) luoshu_text_reboot_mark "${2:-default}" ;;
        reconcile) luoshu_text_reboot_reconcile ;;
        reconcile-rebuild) luoshu_font_rebuild_marker_reconcile ;;
        *) echo 'Usage: font_boot_state.sh {mark FONT|reconcile|reconcile-rebuild}' >&2; exit 2 ;;
    esac
fi
