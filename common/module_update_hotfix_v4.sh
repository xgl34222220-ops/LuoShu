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

# Builder files whose change makes an inherited payload stale. The base list in
# module_update_state.sh predates CJK collection compilation; the composite and
# collection builders and the stage helpers decide which slots/collections exist.
luoshu_v4_builder_compatible() {
    luoshu_update_font_builder_compatible "$1" "$2" || return 1
    for _lvb_relative in \
        common/composite_collection_build.py \
        common/composite_collection_contract.py \
        common/coloros_latin_policy.py \
        common/hyperos_stage_complete.sh \
        common/coloros_stage_complete.sh; do
        [ -e "$1/$_lvb_relative" ] || [ -e "$2/$_lvb_relative" ] || continue
        [ -f "$1/$_lvb_relative" ] && [ -f "$2/$_lvb_relative" ] || return 1
        cmp -s "$1/$_lvb_relative" "$2/$_lvb_relative" || return 1
    done
    return 0
}

# A HyperOS/ColorOS physical payload always carries the stage metrics report
# (slots, compiled CJK collections, preservedCollections reasons). Inherited
# without it, diagnostics cannot tell why NotoSans/SerifCJK stayed stock.
luoshu_v4_payload_needs_report() {
    for _lvn_part in $(luoshu_update_payload_partitions); do
        case "$_lvn_part" in system) _lvn_dir="$1/system/fonts" ;; *) _lvn_dir="$1/$_lvn_part/fonts" ;; esac
        [ -d "$_lvn_dir" ] || continue
        for _lvn_name in MiSansVF.ttf SysSans-En-Regular.ttf SysFont-Regular.ttf; do
            [ -f "$_lvn_dir/$_lvn_name" ] && return 0
        done
    done
    return 1
}

# Carry the payload's metrics report with the payload (the partition copy only
# moves font trees) or mark the inherited payload for one explicit re-apply.
luoshu_v4_carry_payload_report() {
    _lvc_old="$1"; _lvc_new="$2"; _lvc_active="$3"
    LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL=''
    [ "$_lvc_active" != default ] || return 0
    # The flash wrapper may hand us a migration view; source files and the
    # private payload live in the real old module directory.
    _lvc_real="${LUOSHU_UPDATE_REAL_OLD_MOD:-$_lvc_old}"
    _lvc_report="$_lvc_real/.luoshu-payload/.luoshu-metrics-report.json"
    [ -f "$_lvc_report" ] || _lvc_report="$_lvc_old/.luoshu-metrics-report.json"
    if [ "$(luoshu_update_config_value "$_lvc_old/config/font-payload-rebuild-pending.conf" reason)" = font-builder-changed ]; then
        LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL=$(luoshu_update_config_value "$_lvc_old/config/font-payload-rebuild-pending.conf" detail)
        [ -n "$LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL" ] || LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL=builder-files-changed
    elif ! luoshu_v4_builder_compatible "$_lvc_real" "$_lvc_new"; then
        LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL=builder-files-changed
    elif [ ! -f "$_lvc_report" ] && luoshu_v4_payload_needs_report "$_lvc_old"; then
        LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL=metrics-report-missing
    fi
    if [ -z "$LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL" ] && [ -f "$_lvc_report" ]; then
        mkdir -p "$_lvc_new/.luoshu-payload" 2>/dev/null || return 0
        cp -f "$_lvc_report" "$_lvc_new/.luoshu-payload/.luoshu-metrics-report.json" 2>/dev/null || true
        chmod 0644 "$_lvc_new/.luoshu-payload/.luoshu-metrics-report.json" 2>/dev/null || true
    fi
    return 0
}

# The replacement module starts with an empty logs/ directory, which made the
# diagnostic export lose the last apply (its stage log and phase timings). Keep
# the newest part of the previous switch log, bounded like boot housekeeping.
luoshu_v4_carry_switch_log() {
    _lvl_real="${LUOSHU_UPDATE_REAL_OLD_MOD:-$1}"
    _lvl_source=''
    for _lvl_candidate in "$_lvl_real/.luoshu-state/logs/fontswitch.log" "$_lvl_real/logs/fontswitch.log" \
                          "$1/logs/fontswitch.log"; do
        [ -f "$_lvl_candidate" ] && [ -s "$_lvl_candidate" ] && { _lvl_source="$_lvl_candidate"; break; }
    done
    [ -n "$_lvl_source" ] || return 0
    mkdir -p "$2/logs" 2>/dev/null || return 0
    _lvl_dest="$2/logs/fontswitch.log"
    [ ! -L "$_lvl_dest" ] || return 0
    _lvl_tmp="$_lvl_dest.tmp.$$"
    {
        tail -n 1500 "$_lvl_source" 2>/dev/null
        printf '[%s] [UPDATE] module updated; previous switch log carried over\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
        [ ! -f "$_lvl_dest" ] || cat "$_lvl_dest" 2>/dev/null
    } > "$_lvl_tmp" 2>/dev/null && mv -f "$_lvl_tmp" "$_lvl_dest" 2>/dev/null || rm -f "$_lvl_tmp" 2>/dev/null
    chmod 0644 "$_lvl_dest" 2>/dev/null || true
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
    LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL=''
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
        luoshu_v4_carry_payload_report "$_lvm_old" "$_lvm_new" "$_lvm_active"
    else
        luoshu_v4_clear_incompatible_payload "$_lvm_new" || return 1
    fi

    luoshu_migrate_update_cache "$_lvm_old" "$_lvm_new" "$_lvm_compatible"
    luoshu_clear_update_volatile "$_lvm_new" || return 1
    luoshu_v4_carry_switch_log "$_lvm_old" "$_lvm_new"

    # active_font.conf is selection state, never an "effective stock" flag.
    printf '%s\n' "$_lvm_active" > "$_lvm_new/config/active_font.conf" || return 1
    chmod 0644 "$_lvm_new/config/active_font.conf" 2>/dev/null || true

    if [ "$LUOSHU_UPDATE_PAYLOAD_PRESERVED" = true ] && [ -n "${LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL:-}" ]; then
        # The inherited payload keeps working this boot, but it was produced by
        # another builder (or has no metrics/collection report). Only an explicit
        # apply may consume this marker; boot confirmation of the old payload
        # does not prove the new builder ran (font_boot_state.sh).
        LUOSHU_UPDATE_REBUILD_REQUIRED=true
        {
            printf 'state=awaiting-explicit-apply\n'
            printf 'mode=preserve-current\n'
            printf 'reason=font-builder-changed\n'
            printf 'detail=%s\n' "$LUOSHU_UPDATE_PRESERVED_REBUILD_DETAIL"
            printf 'font=%s\n' "$_lvm_active"
            printf 'oldSchema=%s\n' "${_lvm_old_schema:-missing}"
            printf 'newSchema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
        } > "$_lvm_new/config/font-payload-rebuild-pending.conf" 2>/dev/null || return 1
    elif [ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]; then
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
