#!/system/bin/sh
# LuoShu v2.2 transaction guard.
# Every font switch snapshots the complete current payload first, then removes the
# previous device-specific files. If any later stage fails, font_safety.sh restores
# the snapshot including v2 state and XML documents.
set +e

# The installed manifest is the primary ownership record. A damaged/missing manifest
# still must not strand v2 files, so the fallback removes only LuoShu's unique slot
# namespace and XML documents that explicitly reference it.
device_font_payload_clear() {
    _dfpc_module="$(_dfpr_module)"
    type _dfpr_remove_installed_files >/dev/null 2>&1 && _dfpr_remove_installed_files
    for _dfpc_part in $(_luoshu_payload_parts); do
        _dfpc_fonts="$_dfpc_module/$_dfpc_part/fonts"
        if [ -d "$_dfpc_fonts" ]; then
            find "$_dfpc_fonts" -maxdepth 1 -type f -name 'LuoShuSlot-*.ttf' -delete 2>/dev/null || {
                for _dfpc_font in "$_dfpc_fonts"/LuoShuSlot-*.ttf; do
                    [ -f "$_dfpc_font" ] && rm -f "$_dfpc_font" 2>/dev/null || true
                done
            }
        fi
        _dfpc_etc="$_dfpc_module/$_dfpc_part/etc"
        [ -d "$_dfpc_etc" ] || continue
        for _dfpc_xml in "$_dfpc_etc"/*.xml; do
            [ -f "$_dfpc_xml" ] || continue
            grep -q 'LuoShuSlot-' "$_dfpc_xml" 2>/dev/null && rm -f "$_dfpc_xml" 2>/dev/null || true
        done
    done
    rm -f "$_dfpc_module/config/device-font-installed.conf" \
          "$_dfpc_module/config/device-font-engine.conf" \
          "$_dfpc_module/config/device-font-dynamic-mount.conf" \
          "$_dfpc_module/system/etc/.luoshu-data-fonts-config.xml" 2>/dev/null || true
    return 0
}

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
    if ! device_font_payload_clear; then
        rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
        LUOSHU_PAYLOAD_TXN=''
        return 1
    fi
    return 0
}
