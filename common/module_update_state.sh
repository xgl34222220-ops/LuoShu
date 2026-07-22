#!/system/bin/sh
# 模块更新状态迁移：继承当前字体负载，只清理一次性任务与待重启状态。

luoshu_copy_update_tree() {
    _source="$1"
    _destination="$2"
    [ -d "$_source" ] || return 0
    mkdir -p "$_destination" 2>/dev/null || return 1
    cp -af "$_source/." "$_destination/" 2>/dev/null || \
        cp -rfp "$_source/." "$_destination/" 2>/dev/null
}

luoshu_update_config_is_volatile() {
    case "$1" in
        version_notes.conf|switch_task.conf|mix_task.conf|axes_task.conf|emoji_task.conf|\
        text_reboot_required.conf|font_weight_reboot_required.conf|emoji_reboot_required.conf|\
        webui_font_list.json|webui_font_list.key|native_font_index.json|native_font_index.key|\
        composite_progress.json|mix_last_error.txt|app_install_pending|app_install_state.conf|\
        app_install_manual|*.pid|*.pid.task|*.tmp|*.tmp.*)
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

luoshu_migrate_active_install() {
    _old="$1"
    _new="$2"
    [ -f "$_old/module.prop" ] || return 2
    [ "$_old" != "$_new" ] || return 2

    _active=$(head -n1 "$_old/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_active" ] || _active=default
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

    [ -s "$_new/config/active_font.conf" ] || printf '%s\n' "$_active" >"$_new/config/active_font.conf"
    luoshu_clear_update_volatile "$_new"
    chmod 0644 "$_new/config"/* 2>/dev/null || true
    find "$_new/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    return 0
}
