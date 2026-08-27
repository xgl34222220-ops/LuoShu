#!/system/bin/sh
# v4.0.0 update migration hotfix.
# Never turn an update into "restore default". Preserve the selected font and
# rebuild incompatible payloads inside the staged module before the update commits.
set +e

luoshu_v4_clear_incompatible_payload() {
    _lvc_module="$1"
    rm -rf "$_lvc_module/system/fonts" 2>/dev/null || true
    mkdir -p "$_lvc_module/system/fonts" 2>/dev/null || return 1
    rm -f "$_lvc_module/system/etc/fonts.xml" \
          "$_lvc_module/system/etc/font_fallback.xml" 2>/dev/null || true
    for _lvc_part in $(luoshu_update_payload_partitions); do
        [ "$_lvc_part" != system ] || continue
        rm -rf "$_lvc_module/$_lvc_part" 2>/dev/null || true
    done
    rm -rf "$_lvc_module/config/device-font-cache" \
           "$_lvc_module/.font-payload-stage."* \
           "$_lvc_module/.font-payload-backup."* 2>/dev/null || true
    rm -f "$_lvc_module/.font-payload-commit.ok" \
          "$_lvc_module/config/font-payload-schema.conf" \
          "$_lvc_module/config/font-payload-manifest.conf" \
          "$_lvc_module/config/font-payload-boot.conf" \
          "$_lvc_module/config/font-target-aliases.conf" \
          "$_lvc_module/config/font-target-coverage.conf" \
          "$_lvc_module/config/font-config-overlay.conf" 2>/dev/null || true
    return 0
}

# Override the legacy migrator after module_update_state.sh is loaded.
luoshu_migrate_active_install() {
    _lvm_old="$1"
    _lvm_new="$2"
    [ -f "$_lvm_old/module.prop" ] || return 2
    [ "$_lvm_old" != "$_lvm_new" ] || return 2

    _lvm_active=$(head -n1 "$_lvm_old/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lvm_active" ] || _lvm_active=default
    _lvm_old_schema=$(luoshu_update_payload_schema "$_lvm_old")
    _lvm_compatible=false
    [ -n "$_lvm_old_schema" ] && [ "$_lvm_old_schema" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ] && _lvm_compatible=true
    if [ "$_lvm_active" != default ] && ! luoshu_update_has_font_payload "$_lvm_old"; then
        _lvm_compatible=false
    fi

    LUOSHU_UPDATE_ACTIVE="$_lvm_active"
    LUOSHU_UPDATE_OLD_SCHEMA="$_lvm_old_schema"
    LUOSHU_UPDATE_REBUILD_REQUIRED=false
    LUOSHU_UPDATE_PAYLOAD_PRESERVED=false
    [ "$_lvm_active" = default ] || [ "$_lvm_compatible" = true ] || LUOSHU_UPDATE_REBUILD_REQUIRED=true

    mkdir -p "$_lvm_new/config" "$_lvm_new/system/fonts" 2>/dev/null || return 1
    luoshu_migrate_update_config "$_lvm_old" "$_lvm_new" || return 1

    if [ "$_lvm_active" != default ] && [ "$_lvm_compatible" = true ]; then
        for _lvm_rel in system/fonts system/etc; do
            [ -d "$_lvm_old/$_lvm_rel" ] || continue
            rm -rf "$_lvm_new/$_lvm_rel" 2>/dev/null || return 1
            mkdir -p "${_lvm_new}/${_lvm_rel%/*}" 2>/dev/null || return 1
            luoshu_copy_update_tree "$_lvm_old/$_lvm_rel" "$_lvm_new/$_lvm_rel" || return 1
        done
        for _lvm_part in $(luoshu_update_payload_partitions); do
            [ "$_lvm_part" != system ] || continue
            [ -d "$_lvm_old/$_lvm_part" ] || continue
            rm -rf "$_lvm_new/$_lvm_part" 2>/dev/null || return 1
            luoshu_copy_update_tree "$_lvm_old/$_lvm_part" "$_lvm_new/$_lvm_part" || return 1
        done
        LUOSHU_UPDATE_PAYLOAD_PRESERVED=true
    else
        luoshu_v4_clear_incompatible_payload "$_lvm_new" || return 1
    fi

    luoshu_migrate_update_cache "$_lvm_old" "$_lvm_new" "$_lvm_compatible"
    luoshu_clear_update_volatile "$_lvm_new"

    # active_font.conf is selection state, never an "effective stock" flag.
    printf '%s\n' "$_lvm_active" > "$_lvm_new/config/active_font.conf" || return 1
    chmod 0644 "$_lvm_new/config/active_font.conf" 2>/dev/null || true

    if [ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]; then
        {
            printf 'state=install-rebuild-required\n'
            printf 'mode=preserve-selection\n'
            printf 'reason=schema-mismatch\n'
            printf 'font=%s\n' "$_lvm_active"
            printf 'oldSchema=%s\n' "${_lvm_old_schema:-missing}"
            printf 'newSchema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        } > "$_lvm_new/config/font-payload-rebuild-pending.conf" 2>/dev/null || return 1
    fi

    find "$_lvm_new/config" -type d -exec chmod 0755 {} \; 2>/dev/null || true
    find "$_lvm_new/config" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    return 0
}

luoshu_v4_update_rebuild_selected() {
    _lvr_module="$1"
    _lvr_active=$(head -n1 "$_lvr_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lvr_active" ] || _lvr_active=default
    [ "$_lvr_active" != default ] || return 0

    rm -f "$_lvr_module/config/text_reboot_required.conf" \
          "$_lvr_module/config/switch_task.conf" \
          "$_lvr_module/config/mix_task.conf" \
          "$_lvr_module/.font_switch.lock" 2>/dev/null || true
    rm -rf "$_lvr_module/.font_switch.lock" 2>/dev/null || true

    _lvr_started=$(date +%s 2>/dev/null || echo 0)
    if [ "$_lvr_active" = mix ]; then
        _lvr_conf="$_lvr_module/config/font_mix.conf"
        _lvr_cjk=$(sed -n 's/^cjk=//p' "$_lvr_conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        _lvr_latin=$(sed -n 's/^latin=//p' "$_lvr_conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        _lvr_digit=$(sed -n 's/^digit=//p' "$_lvr_conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        [ -n "$_lvr_cjk" ] && [ -n "$_lvr_latin" ] && [ -n "$_lvr_digit" ] || return 1
        MODDIR="$_lvr_module" sh "$_lvr_module/common/font_mix.sh" worker \
            "update-rebuild-${_lvr_started}-$$" "$_lvr_cjk" "$_lvr_latin" "$_lvr_digit" "$_lvr_started" \
            >> "$_lvr_module/logs/fontswitch.log" 2>&1
        _lvr_state=$(sed -n 's/^state=//p' "$_lvr_module/config/mix_task.conf" 2>/dev/null | head -n1)
        [ "$_lvr_state" = success ] || return 1
    else
        _lvr_output=$(MODDIR="$_lvr_module" sh "$_lvr_module/common/font_manager.sh" action switch "$_lvr_active" 2>&1)
        printf '%s\n' "$_lvr_output" >> "$_lvr_module/logs/fontswitch.log" 2>/dev/null || true
        printf '%s\n' "$_lvr_output" | grep -q '"status":"ok"' || return 1
    fi

    _lvr_after=$(head -n1 "$_lvr_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ "$_lvr_after" = "$_lvr_active" ] || return 1
    rm -f "$_lvr_module/config/font-payload-rebuild-pending.conf" \
          "$_lvr_module/config/font-payload-reapply-notified.conf" 2>/dev/null || true
    return 0
}
