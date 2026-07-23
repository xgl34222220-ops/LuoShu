#!/system/bin/sh
# LuoShu v2.2 transaction guard.
# Every font switch snapshots the complete current payload first, then removes the
# previous device-specific files. If any later stage fails, font_safety.sh restores
# the snapshot including v2 state and XML documents.
set +e

luoshu_payload_transaction_begin() {
    [ -z "$LUOSHU_PAYLOAD_TXN" ] || return 1
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE=''
    _lpt_module="$(_luoshu_safety_module)"
    _lpt_config="$(_luoshu_safety_config)"
    LUOSHU_PAYLOAD_TXN="$_lpt_config/.payload-transaction.$$"
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree" "$LUOSHU_PAYLOAD_TXN/config" 2>/dev/null || {
        LUOSHU_PAYLOAD_TXN=''
        return 1
    }
    : > "$LUOSHU_PAYLOAD_TXN/paths" 2>/dev/null || {
        rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
        LUOSHU_PAYLOAD_TXN=''
        return 1
    }

    for _lpt_part in $(_luoshu_payload_parts); do
        for _lpt_sub in fonts etc; do
            _lpt_rel="$_lpt_part/$_lpt_sub"
            _lpt_src="$_lpt_module/$_lpt_rel"
            if [ -d "$_lpt_src" ]; then
                mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_part" 2>/dev/null || {
                    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
                    LUOSHU_PAYLOAD_TXN=''
                    return 1
                }
                cp -al "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null ||
                cp -af "$_lpt_src" "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || {
                    mkdir -p "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel" 2>/dev/null || return 1
                    cp -rfp "$_lpt_src/." "$LUOSHU_PAYLOAD_TXN/tree/$_lpt_rel/" 2>/dev/null || return 1
                }
                printf 'present|%s\n' "$_lpt_rel" >> "$LUOSHU_PAYLOAD_TXN/paths"
            else
                printf 'absent|%s\n' "$_lpt_rel" >> "$LUOSHU_PAYLOAD_TXN/paths"
            fi
        done
    done

    for _lpt_name in \
        active_font.conf font_mix.conf font-config-overlay.conf font-target-aliases.conf \
        font-target-coverage.conf font-payload-manifest.conf font-payload-boot.conf \
        font-payload-schema.conf text_reboot_required.conf device-font-engine.conf \
        device-font-installed.conf device-font-dynamic-mount.conf; do
        if [ -f "$_lpt_config/$_lpt_name" ]; then
            cp -fp "$_lpt_config/$_lpt_name" "$LUOSHU_PAYLOAD_TXN/config/$_lpt_name" 2>/dev/null || {
                rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
                LUOSHU_PAYLOAD_TXN=''
                return 1
            }
            printf 'present|config/%s\n' "$_lpt_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        else
            printf 'absent|config/%s\n' "$_lpt_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        fi
    done

    # The old private device tree must not leak into a direct or composite rebuild.
    # It is removed only after every path above has been snapshotted.
    if type device_font_payload_clear >/dev/null 2>&1; then
        if ! device_font_payload_clear; then
            rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
            LUOSHU_PAYLOAD_TXN=''
            return 1
        fi
    fi
    return 0
}
