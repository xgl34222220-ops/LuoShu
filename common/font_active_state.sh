#!/system/bin/sh
# Metadata-only reuse guard for an already verified font payload.
# Heavy font files are verified once during boot; a repeated identical request must not rebuild them.
set +e

_luoshu_active_state_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_active_state_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_active_payload_verified() {
    _las_expected="${1:-}"
    _las_module="$(_luoshu_active_state_module)"
    _las_config="$_las_module/config"
    _las_active=$(head -n1 "$_las_config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_las_expected" ] && [ "$_las_expected" != default ] || return 1
    [ "$_las_active" = "$_las_expected" ] || return 1
    [ ! -s "$_las_config/text_reboot_required.conf" ] || return 1
    [ ! -s "$_las_config/font-payload-rebuild-pending.conf" ] || return 1
    [ -s "$_las_config/font-payload-manifest.conf" ] || return 1

    _las_boot_state=$(_luoshu_active_state_value "$_las_config/font-payload-boot.conf" state)
    [ "$_las_boot_state" = confirmed ] || return 1

    _las_verify="$_las_config/device-font-load-verification.conf"
    _las_verify_state=$(_luoshu_active_state_value "$_las_verify" state)
    _las_verify_mode=$(_luoshu_active_state_value "$_las_verify" mode)
    _las_verify_active=$(_luoshu_active_state_value "$_las_verify" activeFont)
    [ "$_las_verify_state" = verified ] || return 1
    [ "$_las_verify_active" = "$_las_expected" ] || return 1
    case "$_las_verify_mode" in aligned|mount-verified|mount-confirmed) ;; *) return 1 ;; esac
    [ "$(_luoshu_active_state_value "$_las_config/self-mount.conf" state)" != failed ] || return 1
    return 0
}

_luoshu_mix_state_value() {
    _lms_file="$1"
    _lms_key="$2"
    _lms_fallback="$3"
    _lms_value=$(_luoshu_active_state_value "$_lms_file" "$_lms_key")
    [ -n "$_lms_value" ] || _lms_value="$_lms_fallback"
    printf '%s' "$_lms_value" | tr -d '\r\n'
}

luoshu_mix_request_matches_active() {
    _lms_module="$(_luoshu_active_state_module)"
    _lms_config="$_lms_module/config"
    _lms_source="$_lms_config/axes_mix.conf"
    [ -s "$_lms_source" ] || _lms_source="$_lms_config/font_mix.conf"
    [ -s "$_lms_source" ] || return 1
    luoshu_active_payload_verified mix || return 1

    [ "$(_luoshu_mix_state_value "$_lms_source" cjk '')" = "$1" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" latin '')" = "$2" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" digit '')" = "$3" ] || return 1

    _lms_cjk_weight=$(_luoshu_mix_state_value "$_lms_source" cjkWeight 400)
    _lms_latin_weight=$(_luoshu_mix_state_value "$_lms_source" latinWeight 400)
    _lms_digit_weight=$(_luoshu_mix_state_value "$_lms_source" digitWeight 400)
    [ "$(_luoshu_mix_state_value "$_lms_source" cjkAxes "wght=$_lms_cjk_weight")" = "$4" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" latinAxes "wght=$_lms_latin_weight")" = "$5" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" digitAxes "wght=$_lms_digit_weight")" = "$6" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" cjkMode fixed)" = "${7:-fixed}" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" latinMode fixed)" = "${8:-fixed}" ] || return 1
    [ "$(_luoshu_mix_state_value "$_lms_source" digitMode fixed)" = "${9:-fixed}" ] || return 1
    return 0
}

