#!/system/bin/sh
# Clear every previously generated private font alias before building a new payload.
# This prevents a prior full-CJK switch from leaking tofu-producing aliases into a
# later Latin-only or partial-font switch.
set +e

type _lfrp_payload_root >/dev/null 2>&1 || return 0 2>/dev/null || exit 0

clear_managed_text_fonts() {
    _lfrc_root=$(_lfrp_payload_root)
    for _lfrc_part in $(_lfrp_partitions); do
        rm -rf "$_lfrc_root/$_lfrc_part/fonts" 2>/dev/null || true
        _lfrc_etc="$_lfrc_root/$_lfrc_part/etc"
        [ -d "$_lfrc_etc" ] || continue
        for _lfrc_xml in "$_lfrc_etc"/*.xml; do
            [ -f "$_lfrc_xml" ] || continue
            grep -Eq 'LuoShu(Mono)?-' "$_lfrc_xml" 2>/dev/null && rm -f "$_lfrc_xml" 2>/dev/null || true
        done
    done
    mkdir -p "$_lfrc_root/system/fonts" 2>/dev/null || true
    rm -f "$(_lfrp_target_manifest)" \
        "$(_lfrp_config_root)/font-target-aliases.conf" \
        "$(_lfrp_config_root)/font-target-coverage.conf" \
        "$(_lfrp_config_root)/font-config-overlay.conf" 2>/dev/null || true
}
