#!/system/bin/sh
# 模块更新状态迁移：继承当前字体负载；架构变化只登记一次显式重应用。

LUOSHU_PAYLOAD_SCHEMA_CURRENT="${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-baseline-v10-latin-coverage-v1}"
LUOSHU_UPDATE_ACTIVE=default
LUOSHU_UPDATE_OLD_SCHEMA=''
LUOSHU_UPDATE_REBUILD_REQUIRED=false

# v3.1-v3.3 changed variable-font preparation, XML overlays, HyperOS metrics and
# switch caches in several independent layers.  v3.3.4 and later use the v3.0
# runtime and must not inherit a payload produced before that recovery boundary.
# The reset is one-shot across the boundary: v3.3.4 -> later keeps its payload,
# while a direct v3.1-v3.3 -> later upgrade still receives the safe reset.
luoshu_runtime_recovery_required() {
    _lrr_old="$1"
    _lrr_new="$2"
    [ -f "$_lrr_old/module.prop" ] && [ -f "$_lrr_new/module.prop" ] || return 1
    _lrr_old_code=$(sed -n 's/^versionCode=//p' "$_lrr_old/module.prop" 2>/dev/null | head -n1)
    _lrr_new_code=$(sed -n 's/^versionCode=//p' "$_lrr_new/module.prop" 2>/dev/null | head -n1)
    case "$_lrr_old_code:$_lrr_new_code" in
        *[!0-9:]*|:*|*:) return 1 ;;
    esac
    [ "$_lrr_old_code" -lt 30304 ] && [ "$_lrr_new_code" -ge 30304 ]
}

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
        app_install_manual|font-payload-rebuild-pending.conf|font-payload-reapply-notified.conf|font-boot-failures|\
        font-payload-quarantine.conf|mount_compat.conf|self-mount.conf|\
        self-mount-required.conf|device-font-load-verification.conf|\
        device-font-cache-pending.conf|device-font-cache-failures.conf|\
        device-font-engine.conf|device-font-installed.conf|device-font-dynamic-mount.conf|\
        device-font-load-verification.json|device-font-manager-dump.txt|\
        device-font-mount-evidence.txt|*.pid|*.pid.task|*.tmp|*.tmp.*)
            return 0
            ;;
    esac
    return 1
}

luoshu_update_payload_partitions() {
    if type luoshu_private_partitions >/dev/null 2>&1; then
        luoshu_private_partitions
        return
    fi
    printf '%s\n' \
        'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
}

luoshu_update_has_font_payload() {
    _module="$1"
    for _partition in $(luoshu_update_payload_partitions); do
        case "$_partition" in
            system) _directory="$_module/system/fonts" ;;
            *) _directory="$_module/$_partition" ;;
        esac
        [ -d "$_directory" ] || continue
        find "$_directory" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
            -print -quit 2>/dev/null | grep -q . && return 0
    done
    return 1
}

luoshu_clear_update_volatile() {
    _module="$1"
    if type luoshu_font_lock_force_clear >/dev/null 2>&1; then
        luoshu_font_lock_force_clear "$_module/.font_switch.lock" >/dev/null 2>&1 || true
    else
        rm -f "$_module/.font_switch.lock/pid" 2>/dev/null || true
        rmdir "$_module/.font_switch.lock" 2>/dev/null || true
        rm -f "$_module"/.font_switch.lock.owner.* 2>/dev/null || true
    fi
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
        "$_module/config/font-payload-reapply-notified.conf" \
        "$_module/config/device-font-cache-pending.conf" \
        "$_module/config/device-font-cache-failures.conf" \
        "$_module/config/device-font-engine.conf" \
        "$_module/config/device-font-installed.conf" \
        "$_module/config/device-font-dynamic-mount.conf" \
        "$_module/config/mount_compat.conf" \
        "$_module/config/self-mount.conf" \
        "$_module/config/self-mount-required.conf" \
        "$_module/config/device-font-load-verification.conf" \
        "$_module/config/device-font-load-verification.json" \
        "$_module/config/device-font-manager-dump.txt" \
        "$_module/config/device-font-mount-evidence.txt" \
        "$_module/.font_switch.lock" \
        "$_module/.font-payload-commit.ok" 2>/dev/null || true
    rm -f "$_module/config"/*.pid "$_module/config"/*.pid.task \
        "$_module/config"/*.tmp "$_module/config"/*.tmp.* 2>/dev/null || true
    rm -rf "$_module"/.font-payload-stage.* "$_module"/.font-payload-backup.* 2>/dev/null || true
    if [ -e "$_module/.device-font-cache.lock" ]; then
        if type luoshu_font_lock_reap_stale >/dev/null 2>&1; then
            luoshu_font_lock_reap_stale "$_module/.device-font-cache.lock" >/dev/null 2>&1 || true
        fi
    fi
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
    _schema_compatible="${3:-false}"
    for _relative in \
        cache/full-composite-v11 \
        cache/auto-multiweight-mix/composites-v8 \
        cache/auto-multiweight-mix/prepared-v8 \
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

    # Config contains persistent immutable artifacts as directories. The old migrator copied only
    # regular files from config/*, silently dropping the entire device alignment cache on update.
    # Metric/source caches are content-addressed and safe across releases. A device payload cache is
    # retained only when its payload schema is unchanged.
    for _relative in config/metrics_cache config/font-config-source; do
        [ -d "$_old/$_relative" ] || continue
        rm -rf "$_new/$_relative" 2>/dev/null || true
        mkdir -p "${_new}/${_relative%/*}" 2>/dev/null || continue
        luoshu_copy_update_tree "$_old/$_relative" "$_new/$_relative" || true
    done
    if [ "$_schema_compatible" = true ] && [ -d "$_old/config/device-font-cache" ]; then
        rm -rf "$_new/config/device-font-cache" 2>/dev/null || true
        mkdir -p "$_new/config" 2>/dev/null || true
        luoshu_copy_update_tree "$_old/config/device-font-cache" "$_new/config/device-font-cache" || true
    fi
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
    if [ "$_active" = mix ]; then
        for _mix_key in cjk latin digit; do
            [ -n "$(luoshu_update_config_value "$_old/config/font_mix.conf" "$_mix_key")" ] || return 1
        done
    fi
    if [ "$_active" != default ] && ! luoshu_update_has_font_payload "$_old"; then
        return 1
    fi

    mkdir -p "$_new/config" "$_new/system/fonts" 2>/dev/null || return 1
    luoshu_migrate_update_config "$_old" "$_new" || return 1

    # Keep the new release's system/bin runtime, but migrate both system font
    # trees and every supported OEM partition from the active installation.
    for _relative in system/fonts system/etc; do
        [ -d "$_old/$_relative" ] || continue
        rm -rf "$_new/$_relative" 2>/dev/null || return 1
        mkdir -p "${_new}/${_relative%/*}" 2>/dev/null || return 1
        luoshu_copy_update_tree "$_old/$_relative" "$_new/$_relative" || return 1
    done
    for _partition in $(luoshu_update_payload_partitions); do
        [ "$_partition" != system ] || continue
        [ -d "$_old/$_partition" ] || continue
        rm -rf "$_new/$_partition" 2>/dev/null || return 1
        mkdir -p "$_new" 2>/dev/null || return 1
        luoshu_copy_update_tree "$_old/$_partition" "$_new/$_partition" || return 1
    done

    _schema_compatible=false
    [ "$_old_schema" = "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" ] && _schema_compatible=true
    luoshu_migrate_update_cache "$_old" "$_new" "$_schema_compatible"
    luoshu_clear_update_volatile "$_new"
    # active_font.conf is the selection authority. Write the captured value after cleanup so a
    # packaged default or a partial config copy can never relabel an inherited composite as default.
    printf '%s\n' "$_active" >"$_new/config/active_font.conf" || return 1
    if [ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]; then
        {
            printf 'state=awaiting-explicit-apply\n'
            printf 'mode=preserve-current\n'
            printf 'reason=schema-upgrade\n'
            printf 'font=%s\n' "$_active"
            printf 'oldSchema=%s\n' "${_old_schema:-missing}"
            printf 'newSchema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT"
            printf 'time=%s\n' "$(date +%s)"
        } > "$_new/config/font-payload-rebuild-pending.conf" 2>/dev/null || return 1
        rm -f "$_new/config/font-payload-reapply-notified.conf" 2>/dev/null || true
    fi
    find "$_new/config" -type d -exec chmod 0755 {} \; 2>/dev/null || true
    find "$_new/config" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    find "$_new/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    return 0
}
