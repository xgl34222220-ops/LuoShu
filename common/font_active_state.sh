#!/system/bin/sh
# Metadata-only reuse guard for an already verified font payload.
# Heavy font files are verified once during boot; a repeated identical request must not rebuild them.
set +e

_luoshu_active_provenance_load() {
    _lap_module="$(_luoshu_active_state_module)"
    _lap_helper="$_lap_module/common/font_provenance.sh"
    [ -f "$_lap_helper" ] || return 1
    type luoshu_provenance_direct_proof >/dev/null 2>&1 || . "$_lap_helper" || return 1
    type luoshu_provenance_direct_proof >/dev/null 2>&1
}

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

    # Reuse only byte evidence still bound to this boot and payload manifest.
    # This status path checks metadata; it never reads large font files again.
    [ -f "$_las_module/common/device_font_load_verify.sh" ] || return 1
    MODDIR="$_las_module" MODULE_DIR="$_las_module" \
        sh "$_las_module/common/device_font_load_verify.sh" status >/dev/null 2>&1 || return 1

    _las_verify="$_las_config/device-font-load-verification.conf"
    _las_verify_state=$(_luoshu_active_state_value "$_las_verify" state)
    _las_verify_mode=$(_luoshu_active_state_value "$_las_verify" mode)
    _las_verify_active=$(_luoshu_active_state_value "$_las_verify" activeFont)
    [ "$_las_verify_state" = verified ] || return 1
    [ "$_las_verify_active" = "$_las_expected" ] || return 1
    case "$_las_verify_mode" in aligned|mount-verified|mount-confirmed) ;; *) return 1 ;; esac
    [ "$(_luoshu_active_state_value "$_las_config/self-mount.conf" state)" != failed ] || return 1

    # A direct-font no-op is safe only when the exact source bytes, installed
    # inventory and generation engine still match the payload activated at boot.
    # Older payloads intentionally miss this proof and are rebuilt once.
    if [ "$_las_expected" != mix ]; then
        _las_source="${2:-}"
        [ -f "$_las_source" ] || return 1
        _las_activated="$_las_config/font-payload-activated.conf"
        [ "$(_luoshu_active_state_value "$_las_activated" font)" = "$_las_expected" ] || return 1
        [ "$(_luoshu_active_state_value "$_las_activated" provenanceSchema)" = font-provenance-v1 ] || return 1
        [ "$(_luoshu_active_state_value "$_las_activated" proofKind)" = direct ] || return 1
        _luoshu_active_provenance_load || return 1
        _las_current_proof=$(luoshu_provenance_direct_proof "$_las_source" "$_las_expected") || return 1
        [ "$(_luoshu_active_state_value "$_las_activated" directProof)" = "$_las_current_proof" ] || return 1
    fi
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

    [ "$(_luoshu_mix_state_value "$_lms_source" provenanceSchema '')" = font-provenance-v1 ] || return 1
    _lms_saved_proof=$(_luoshu_mix_state_value "$_lms_source" mixProof '')
    [ -n "$_lms_saved_proof" ] || return 1
    _luoshu_active_provenance_load || return 1
    _lms_fonts="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
    _lms_current_proof=$(luoshu_provenance_mix_proof         "$1" "$2" "$3" "$4" "$5" "$6"         "${7:-fixed}" "${8:-fixed}" "${9:-fixed}" "$_lms_fonts") || return 1
    [ "$_lms_saved_proof" = "$_lms_current_proof" ] || return 1
    return 0
}

