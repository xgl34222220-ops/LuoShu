#!/system/bin/sh
# 模块更新状态迁移：继承当前字体负载，并在引擎架构变化时自动重建。

LUOSHU_PAYLOAD_SCHEMA_CURRENT="${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-baseline-v7-mono-v4}"
LUOSHU_UPDATE_ACTIVE=default
LUOSHU_UPDATE_OLD_SCHEMA=''
LUOSHU_UPDATE_REBUILD_REQUIRED=false
LUOSHU_UPDATE_REBUILT=false
LUOSHU_UPDATE_REBUILD_FAILED=false

luoshu_update_payload_schema() {
    sed -n 's/^schema=//p' "$1/config/font-payload-schema.conf" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_update_config_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}


luoshu_copy_update_tree() {
    _source="$1"
    _destination="$2"
    [ -d "$_source" ] || return 0
    mkdir -p "$_destination" 2>/dev/null || return 1
    cp -al "$_source/." "$_destination/" 2>/dev/null || \
        cp -af "$_source/." "$_destination/" 2>/dev/null || \
        cp -rfp "$_source/." "$_destination/" 2>/dev/null
}

luoshu_update_config_is_volatile() {
    case "$1" in
        version_notes.conf|switch_task.conf|mix_task.conf|axes_task.conf|emoji_task.conf|\
        text_reboot_required.conf|font_weight_reboot_required.conf|emoji_reboot_required.conf|\
        webui_font_list.json|webui_font_list.key|native_font_index.json|native_font_index.key|\
        composite_progress.json|mix_last_error.txt|app_install_pending|app_install_state.conf|\
        app_install_manual|font-payload-rebuild-pending.conf|font-boot-failures|\
        font-payload-quarantine.conf|*.pid|*.pid.task|*.tmp|*.tmp.*)
            return 0
            ;;
    esac
    return 1
}

luoshu_update_has_font_payload() {
    _module="$1"
    for _directory in \
        "$_module/system/fonts" \
        "$_module/system_ext" \
        "$_module/product" \
        "$_module/vendor" \
        "$_module/odm" \
        "$_module/oem" \
        "$_module/my_product"; do
        [ -d "$_directory" ] || continue
        find "$_directory" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
            -print -quit 2>/dev/null | grep -q . && return 0
    done
    return 1
}

luoshu_clear_update_volatile() {
    _module="$1"
    rm -f \
        "$_module/config/switch_task.conf" \
        "$_module/config/mix_task.conf" \
        "$_module/config/axes_task.conf" \
        "$_module/config/emoji_task.conf" \
        "$_module/config/text_reboot_required.conf" \
        "$_module/config/font_weight_reboot_required.conf" \
        "$_module/config/emoji_reboot_required.conf" \
        "$_module/config/webui_font_list.json" \
        "$_module/config/webui_font_list.key" \
        "$_module/config/native_font_index.json" \
        "$_module/config/native_font_index.key" \
        "$_module/config/composite_progress.json" \
        "$_module/config/mix_last_error.txt" \
        "$_module/config/app_install_pending" \
        "$_module/config/app_install_state.conf" \
        "$_module/config/app_install_manual" \
        "$_module/config/font-payload-rebuild-pending.conf" \
        "$_module/.font_switch.lock" \
        "$_module/.font-payload-commit.ok" 2>/dev/null || true
    rm -f "$_module/config"/*.pid "$_module/config"/*.pid.task \
        "$_module/config"/*.tmp "$_module/config"/*.tmp.* 2>/dev/null || true
    rm -rf "$_module"/.font-payload-stage.* "$_module"/.font-payload-backup.* 2>/dev/null || true
}

luoshu_migrate_update_config() {
    _old="$1"
    _new="$2"
    [ -d "$_old/config" ] || return 0
    mkdir -p "$_new/config" 2>/dev/null || return 1
    for _source in "$_old/config"/*; do
        [ -f "$_source" ] || continue
        _name=${_source##*/}
        luoshu_update_config_is_volatile "$_name" && continue
        cp -af "$_source" "$_new/config/$_name" 2>/dev/null || \
            cp -fp "$_source" "$_new/config/$_name" 2>/dev/null || return 1
    done
    return 0
}

luoshu_migrate_update_cache() {
    _old="$1"
    _new="$2"
    for _relative in \
        cache/full-composite-v9 \
        cache/auto-multiweight-mix/composites-v6 \
        cache/auto-multiweight-mix/prepared-v6 \
        cache/auto-multiweight-mix/source-meta-v1; do
        [ -d "$_old/$_relative" ] || continue
        rm -rf "$_new/$_relative" 2>/dev/null || true
        mkdir -p "${_new}/${_relative%/*}" 2>/dev/null || continue
        luoshu_copy_update_tree "$_old/$_relative" "$_new/$_relative" || true
    done
    mkdir -p "$_new/cache" 2>/dev/null || true
    for _probe in "$_old/cache"/runtime_probe.*.ok; do
        [ -f "$_probe" ] || continue
        cp -al "$_probe" "$_new/cache/${_probe##*/}" 2>/dev/null || \
            cp -af "$_probe" "$_new/cache/${_probe##*/}" 2>/dev/null || true
    done
}

luoshu_migrate_active_install() {
    _old="$1"
    _new="$2"
    [ -f "$_old/module.prop" ] || return 2
    [ "$_old" != "$_new" ] || return 2

    _active=$(head -n1 "$_old/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_active" ] || _active=default
    _old_schema=$(luoshu_update_payload_schema "$_old")
    LUOSHU_UPDATE_ACTIVE="$_active"
    LUOSHU_UPDATE_OLD_SCHEMA="$_old_schema"
    LUOSHU_UPDATE_REBUILD_REQUIRED=false
    [ "$_active" = default ] || [ "$_old_schema" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ] || LUOSHU_UPDATE_REBUILD_REQUIRED=true
    if [ "$_active" != default ] && ! luoshu_update_has_font_payload "$_old"; then
        return 1
    fi

    mkdir -p "$_new/config" "$_new/system/fonts" 2>/dev/null || return 1
    luoshu_migrate_update_config "$_old" "$_new" || return 1

    for _relative in system/fonts system/etc system_ext product vendor odm oem my_product; do
        [ -d "$_old/$_relative" ] || continue
        rm -rf "$_new/$_relative" 2>/dev/null || return 1
        mkdir -p "${_new}/${_relative%/*}" 2>/dev/null || return 1
        luoshu_copy_update_tree "$_old/$_relative" "$_new/$_relative" || return 1
    done

    luoshu_migrate_update_cache "$_old" "$_new"
    [ -s "$_new/config/active_font.conf" ] || printf '%s\n' "$_active" >"$_new/config/active_font.conf"
    luoshu_clear_update_volatile "$_new"
    if [ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]; then
        {
            printf 'state=pending\n'
            printf 'font=%s\n' "$_active"
            printf 'oldSchema=%s\n' "${_old_schema:-missing}"
            printf 'newSchema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'time=%s\n' "$(date +%s)"
        } > "$_new/config/font-payload-rebuild-pending.conf" 2>/dev/null || return 1
    fi
    chmod 0644 "$_new/config"/* 2>/dev/null || true
    find "$_new/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    return 0
}


luoshu_update_task_failed() {
    _lut_module="$1"
    for _lut_task in axes_task.conf mix_task.conf; do
        _lut_state=$(luoshu_update_config_value "$_lut_module/config/$_lut_task" state)
        [ "$_lut_state" != failed ] || return 0
    done
    return 1
}

luoshu_wait_for_payload_schema() {
    _luw_module="$1"
    _luw_timeout="${2:-${LUOSHU_UPDATE_REBUILD_TIMEOUT:-900}}"
    case "$_luw_timeout" in ''|*[!0-9]*) _luw_timeout=900 ;; esac
    _luw_elapsed=0
    while [ "$_luw_elapsed" -le "$_luw_timeout" ]; do
        _luw_schema=$(luoshu_update_payload_schema "$_luw_module")
        [ "$_luw_schema" != "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ] || return 0
        luoshu_update_task_failed "$_luw_module" && return 1
        sleep 2
        _luw_elapsed=$((_luw_elapsed + 2))
    done
    return 1
}

luoshu_rebuild_preserved_payload() {
    _lur_module="$1"
    _lur_active="${LUOSHU_UPDATE_ACTIVE:-default}"
    [ -n "$_lur_active" ] || _lur_active=$(head -n1 "$_lur_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lur_active" ] || _lur_active=default
    LUOSHU_UPDATE_REBUILT=false
    LUOSHU_UPDATE_REBUILD_FAILED=false
    rm -f "$_lur_module/config/text_reboot_required.conf" "$_lur_module/.font_switch.lock" \
          "$_lur_module/config/axes_task.conf" "$_lur_module/config/mix_task.conf" \
          "$_lur_module/config/font-payload-schema.conf" 2>/dev/null || true

    if [ "$_lur_active" = default ]; then
        mkdir -p "$_lur_module/config" 2>/dev/null || return 1
        {
            printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'font=default\n'
            printf 'time=%s\n' "$(date +%s)"
        } > "$_lur_module/config/font-payload-schema.conf" 2>/dev/null || return 1
    elif [ "$_lur_active" = mix ]; then
        _lur_conf="$_lur_module/config/axes_mix.conf"
        [ -s "$_lur_conf" ] || _lur_conf="$_lur_module/config/font_mix.conf"
        _lur_cjk=$(luoshu_update_config_value "$_lur_conf" cjk)
        _lur_latin=$(luoshu_update_config_value "$_lur_conf" latin)
        _lur_digit=$(luoshu_update_config_value "$_lur_conf" digit)
        _lur_cjk_axes=$(luoshu_update_config_value "$_lur_conf" cjkAxes)
        _lur_latin_axes=$(luoshu_update_config_value "$_lur_conf" latinAxes)
        _lur_digit_axes=$(luoshu_update_config_value "$_lur_conf" digitAxes)
        [ -n "$_lur_cjk_axes" ] || _lur_cjk_axes="wght=$(luoshu_update_config_value "$_lur_conf" cjkWeight)"
        [ -n "$_lur_latin_axes" ] || _lur_latin_axes="wght=$(luoshu_update_config_value "$_lur_conf" latinWeight)"
        [ -n "$_lur_digit_axes" ] || _lur_digit_axes="wght=$(luoshu_update_config_value "$_lur_conf" digitWeight)"
        case "$_lur_cjk_axes" in wght=) _lur_cjk_axes=wght=400 ;; esac
        case "$_lur_latin_axes" in wght=) _lur_latin_axes=wght=400 ;; esac
        case "$_lur_digit_axes" in wght=) _lur_digit_axes=wght=400 ;; esac
        _lur_cjk_mode=$(luoshu_update_config_value "$_lur_conf" cjkMode); [ -n "$_lur_cjk_mode" ] || _lur_cjk_mode=infer
        _lur_latin_mode=$(luoshu_update_config_value "$_lur_conf" latinMode); [ -n "$_lur_latin_mode" ] || _lur_latin_mode=infer
        _lur_digit_mode=$(luoshu_update_config_value "$_lur_conf" digitMode); [ -n "$_lur_digit_mode" ] || _lur_digit_mode=infer
        _lur_result=$(MODDIR="$_lur_module" sh "$_lur_module/common/font_mix_controller.sh" start \
            "$_lur_cjk" "$_lur_latin" "$_lur_digit" \
            "$_lur_cjk_axes" "$_lur_latin_axes" "$_lur_digit_axes" \
            "$_lur_cjk_mode" "$_lur_latin_mode" "$_lur_digit_mode" 2>&1)
        printf '%s\n' "$_lur_result" >> "$_lur_module/logs/fontswitch.log" 2>/dev/null || true
        printf '%s\n' "$_lur_result" | grep -q '"status":"ok"' || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
        luoshu_wait_for_payload_schema "$_lur_module" || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
    else
        _lur_result=$(MODDIR="$_lur_module" sh "$_lur_module/common/font_manager.sh" action switch "$_lur_active" 2>&1)
        printf '%s\n' "$_lur_result" >> "$_lur_module/logs/fontswitch.log" 2>/dev/null || true
        printf '%s\n' "$_lur_result" | grep -q '"status":"ok"' || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
        luoshu_wait_for_payload_schema "$_lur_module" 30 || { LUOSHU_UPDATE_REBUILD_FAILED=true; return 1; }
    fi

    rm -f "$_lur_module/config/font-payload-rebuild-pending.conf" 2>/dev/null || true
    rm -f "$_lur_module/config/font-payload-rebuild-failures" 2>/dev/null || true
    LUOSHU_UPDATE_REBUILT=true
    return 0
}

# 重建失败时的重试记账：旧负载仍按原架构挂载并可正常使用，直接隔离会把用户
# 正在用的字体误删。先保留负载并留下待重建标记，下次开机重试；连续失败达到
# 上限后才允许调用方走隔离兜底。
luoshu_rebuild_failure_retry() {
    _lrfr_module="$1"
    _lrfr_limit="${2:-3}"
    _lrfr_count=$(cat "$_lrfr_module/config/font-payload-rebuild-failures" 2>/dev/null)
    case "$_lrfr_count" in ''|*[!0-9]*) _lrfr_count=0 ;; esac
    _lrfr_count=$((_lrfr_count + 1))
    printf '%s\n' "$_lrfr_count" > "$_lrfr_module/config/font-payload-rebuild-failures" 2>/dev/null || true
    [ "$_lrfr_count" -lt "$_lrfr_limit" ]
}
