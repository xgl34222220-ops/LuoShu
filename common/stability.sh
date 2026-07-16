#!/system/bin/sh
# 洛书 v13.5 Stable Hotfix2 - 独立稳定性、自救与 ROM 诊断工具
# 该脚本不依赖 WebUI 主逻辑；即使字体列表加载失败，也可单独执行。

set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    elif [ -f "/data/adb/modules/LuoShu/module.prop" ]; then
        MODDIR="/data/adb/modules/LuoShu"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODULE_DIR/config"
RECOVERY_DIR="$CONFIG_DIR/recovery"
LOG_DIR="$MODULE_DIR/logs"
PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
FONTS_DIR="$PUBLIC_DIR/fonts"
EMOJI_DIR="$PUBLIC_DIR/emoji"
REPORT_DIR="$PUBLIC_DIR/reports"
FONT_MANAGER="$MODULE_DIR/common/font_manager.sh"
CURRENT_STATE="$RECOVERY_DIR/current.state"
PREVIOUS_STATE="$RECOVERY_DIR/previous.state"
LAST_SCAN="$RECOVERY_DIR/last_scan.state"
ROM_PROFILE="$RECOVERY_DIR/rom_profile.state"

mkdir -p "$RECOVERY_DIR" "$LOG_DIR" "$FONTS_DIR" "$EMOJI_DIR" "$REPORT_DIR" 2>/dev/null || true

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\r/\\r/g; s/\n/\\n/g'
}

read_first() {
    _file="$1"; _fallback="$2"
    _value=""
    [ -f "$_file" ] && _value=$(head -n1 "$_file" 2>/dev/null | tr -d '\r\n')
    [ -n "$_value" ] || _value="$_fallback"
    printf '%s' "$_value"
}

read_kv() {
    _file="$1"; _key="$2"; _fallback="$3"
    _value=""
    [ -f "$_file" ] && _value=$(sed -n "s/^${_key}=//p" "$_file" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_value" ] || _value="$_fallback"
    printf '%s' "$_value"
}

bool_json() {
    [ "$1" = "true" ] && printf true || printf false
}

prop() {
    _key="$1"
    if command -v getprop >/dev/null 2>&1; then
        getprop "$_key" 2>/dev/null
    else
        printf ''
    fi
}

count_font_files() {
    _dir="$1"
    [ -d "$_dir" ] || { printf 0; return; }
    find "$_dir" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) 2>/dev/null | wc -l | tr -d '[:space:]'
}

state_font() { read_first "$CONFIG_DIR/active_font.conf" default; }
state_emoji() { read_first "$CONFIG_DIR/active_emoji.conf" default; }
state_weight() { read_kv "$CONFIG_DIR/font_weight.conf" adjustment 0; }

write_state_file() {
    _target="$1"
    _font="$(state_font)"
    _emoji="$(state_emoji)"
    _weight="$(state_weight)"
    _now=$(date +%s 2>/dev/null || echo 0)
    {
        printf 'font=%s\n' "$_font"
        printf 'emoji=%s\n' "$_emoji"
        printf 'weight=%s\n' "$_weight"
        printf 'saved_at=%s\n' "$_now"
    } > "$_target.tmp" 2>/dev/null && mv -f "$_target.tmp" "$_target" 2>/dev/null
}

state_signature() {
    _file="$1"
    [ -f "$_file" ] || { printf ''; return; }
    printf '%s|%s|%s' \
        "$(read_kv "$_file" font default)" \
        "$(read_kv "$_file" emoji default)" \
        "$(read_kv "$_file" weight 0)"
}

live_signature() {
    printf '%s|%s|%s' "$(state_font)" "$(state_emoji)" "$(state_weight)"
}

detect_root_manager() {
    if [ -d /data/adb/ksu ]; then printf 'KernelSU'
    elif [ -d /data/adb/ap ]; then printf 'APatch'
    elif [ -d /data/adb/magisk ]; then printf 'Magisk'
    elif [ -d /data/adb/modules ]; then printf 'Root 模块环境'
    else printf '未知'
    fi
}

detect_rom() {
    _manufacturer=$(prop ro.product.manufacturer)
    _brand=$(prop ro.product.brand)
    _display=$(prop ro.build.display.id)
    _oplus=$(prop ro.build.version.oplusrom)
    _miui=$(prop ro.miui.ui.version.name)
    _hyper=$(prop ro.mi.os.version.name)
    _oneui=$(prop ro.build.version.oneui)
    _all=$(printf '%s %s %s %s %s %s %s' "$_manufacturer" "$_brand" "$_display" "$_oplus" "$_miui" "$_hyper" "$_oneui" | tr '[:upper:]' '[:lower:]')
    case "$_all" in
        *oppo*|*oneplus*|*realme*|*coloros*|*oxygenos*) printf 'ColorOS / OxygenOS' ;;
        *xiaomi*|*redmi*|*poco*|*hyperos*|*miui*) printf 'HyperOS / MIUI' ;;
        *samsung*|*oneui*) printf 'One UI' ;;
        *meizu*|*flyme*) printf 'Flyme' ;;
        *google*|*pixel*) printf 'AOSP / Pixel' ;;
        *) printf 'AOSP / 其他 ROM' ;;
    esac
}

list_font_configs() {
    _out=""
    for _f in \
        /system/etc/fonts.xml \
        /system/etc/fonts_fallback.xml \
        /system/etc/fonts_customization.xml \
        /system/system_ext/etc/fonts_base.xml \
        /system/system_ext/etc/fonts_ule.xml \
        /system/system_ext/etc/fonts_fallback.xml \
        /system/product/etc/fonts_customization.xml \
        /product/etc/fonts_customization.xml \
        /system_ext/etc/fonts_base.xml \
        /system_ext/etc/fonts_ule.xml; do
        [ -f "$_f" ] || continue
        [ -n "$_out" ] && _out="$_out,"
        _out="$_out$_f"
    done
    printf '%s' "$_out"
}

save_rom_profile() {
    _rom="$(detect_rom)"
    _sdk="$(prop ro.build.version.sdk)"
    _release="$(prop ro.build.version.release)"
    _configs="$(list_font_configs)"
    {
        printf 'rom=%s\n' "$_rom"
        printf 'sdk=%s\n' "${_sdk:-unknown}"
        printf 'android=%s\n' "${_release:-unknown}"
        printf 'root=%s\n' "$(detect_root_manager)"
        printf 'configs=%s\n' "$_configs"
        printf 'detected_at=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$ROM_PROFILE.tmp" 2>/dev/null && mv -f "$ROM_PROFILE.tmp" "$ROM_PROFILE" 2>/dev/null
}

save_snapshot_internal() {
    _mode="${1:-boot}"
    save_rom_profile
    write_state_file "$RECOVERY_DIR/candidate.state"
    if [ ! -s "$RECOVERY_DIR/candidate.state" ]; then
        printf '{"status":"error","message":"稳定快照写入失败，请先修复脚本权限"}\n'
        return 1
    fi
    _candidate_sig=$(state_signature "$RECOVERY_DIR/candidate.state")
    _current_sig=$(state_signature "$CURRENT_STATE")
    if [ ! -s "$CURRENT_STATE" ]; then
        mv -f "$RECOVERY_DIR/candidate.state" "$CURRENT_STATE" 2>/dev/null
        printf '{"status":"ok","message":"已建立首个稳定配置快照"}\n'
        return 0
    fi
    if [ "$_candidate_sig" != "$_current_sig" ]; then
        cp -f "$CURRENT_STATE" "$PREVIOUS_STATE" 2>/dev/null || true
        mv -f "$RECOVERY_DIR/candidate.state" "$CURRENT_STATE" 2>/dev/null
        printf '{"status":"ok","message":"已保存当前稳定快照，原快照已成为可回滚配置"}\n'
    elif [ "$_mode" = "manual" ]; then
        mv -f "$RECOVERY_DIR/candidate.state" "$CURRENT_STATE" 2>/dev/null
        printf '{"status":"ok","message":"当前配置未变化，已刷新稳定快照保存时间"}\n'
    else
        rm -f "$RECOVERY_DIR/candidate.state" 2>/dev/null
        printf '{"status":"ok","message":"稳定配置未变化"}\n'
    fi
}

boot_snapshot() { save_snapshot_internal boot; }
manual_snapshot() { save_snapshot_internal manual; }

status_json() {
    save_rom_profile
    _module_ok=false; [ -r "$MODULE_DIR/module.prop" ] && _module_ok=true
    _script_ok=false; [ -x "$FONT_MANAGER" ] && [ -x "$MODULE_DIR/common/stability.sh" ] && _script_ok=true
    _fonts_ok=false; [ -d "$FONTS_DIR" ] && [ -r "$FONTS_DIR" ] && _fonts_ok=true
    _version=$(sed -n 's/^version=//p' "$MODULE_DIR/module.prop" 2>/dev/null | head -n1)
    _current_font="$(state_font)"
    _current_emoji="$(state_emoji)"
    _weight="$(state_weight)"
    _snapshot_font=$(read_kv "$CURRENT_STATE" font '')
    _snapshot_emoji=$(read_kv "$CURRENT_STATE" emoji '')
    _snapshot_weight=$(read_kv "$CURRENT_STATE" weight '')
    _snapshot_saved_at=$(read_kv "$CURRENT_STATE" saved_at 0)
    _previous_font=$(read_kv "$PREVIOUS_STATE" font '')
    _previous_emoji=$(read_kv "$PREVIOUS_STATE" emoji '')
    _previous_weight=$(read_kv "$PREVIOUS_STATE" weight '')
    _previous_saved_at=$(read_kv "$PREVIOUS_STATE" saved_at 0)
    case "$_snapshot_saved_at" in ''|*[!0-9]*) _snapshot_saved_at=0 ;; esac
    case "$_previous_saved_at" in ''|*[!0-9]*) _previous_saved_at=0 ;; esac
    _snapshot_exists=false; [ -s "$CURRENT_STATE" ] && _snapshot_exists=true
    _snapshot_matches=false
    [ "$_snapshot_exists" = true ] && [ "$(live_signature)" = "$(state_signature "$CURRENT_STATE")" ] && _snapshot_matches=true
    _rollback_available=false; [ -s "$PREVIOUS_STATE" ] && [ -n "$_previous_font" ] && _rollback_available=true
    _rom=$(read_kv "$ROM_PROFILE" rom "$(detect_rom)")
    _sdk=$(read_kv "$ROM_PROFILE" sdk "$(prop ro.build.version.sdk)")
    _android=$(read_kv "$ROM_PROFILE" android "$(prop ro.build.version.release)")
    _root=$(read_kv "$ROM_PROFILE" root "$(detect_root_manager)")
    _configs=$(read_kv "$ROM_PROFILE" configs "$(list_font_configs)")
    _scan_ms=$(read_kv "$LAST_SCAN" duration_ms 0)
    _scan_result=$(read_kv "$LAST_SCAN" result never)
    _scan_at=$(read_kv "$LAST_SCAN" finished_at 0)
    _font_count=$(count_font_files "$FONTS_DIR")
    _emoji_count=$(count_font_files "$EMOJI_DIR")
    [ -n "$_font_count" ] || _font_count=0
    [ -n "$_emoji_count" ] || _emoji_count=0
    printf '{"status":"ok","data":{'
    printf '"version":"%s",' "$(json_escape "$_version")"
    printf '"moduleReadable":%s,' "$(bool_json "$_module_ok")"
    printf '"scriptsExecutable":%s,' "$(bool_json "$_script_ok")"
    printf '"fontsReadable":%s,' "$(bool_json "$_fonts_ok")"
    printf '"fontFiles":%s,"emojiFiles":%s,' "$_font_count" "$_emoji_count"
    printf '"currentFont":"%s","currentEmoji":"%s","weight":"%s",' "$(json_escape "$_current_font")" "$(json_escape "$_current_emoji")" "$(json_escape "$_weight")"
    printf '"snapshotFont":"%s","snapshotEmoji":"%s","snapshotWeight":"%s","snapshotSavedAt":%s,' "$(json_escape "$_snapshot_font")" "$(json_escape "$_snapshot_emoji")" "$(json_escape "$_snapshot_weight")" "$_snapshot_saved_at"
    printf '"snapshotExists":%s,"snapshotMatchesCurrent":%s,' "$(bool_json "$_snapshot_exists")" "$(bool_json "$_snapshot_matches")"
    printf '"previousFont":"%s","previousEmoji":"%s","previousWeight":"%s","previousSavedAt":%s,"rollbackAvailable":%s,' "$(json_escape "$_previous_font")" "$(json_escape "$_previous_emoji")" "$(json_escape "$_previous_weight")" "$_previous_saved_at" "$(bool_json "$_rollback_available")"
    printf '"rom":"%s","android":"%s","sdk":"%s","root":"%s","fontConfigs":"%s",' "$(json_escape "$_rom")" "$(json_escape "$_android")" "$(json_escape "$_sdk")" "$(json_escape "$_root")" "$(json_escape "$_configs")"
    printf '"lastScanMs":%s,"lastScanResult":"%s","lastScanAt":%s' "${_scan_ms:-0}" "$(json_escape "$_scan_result")" "${_scan_at:-0}"
    printf '}}\n'
}

clear_cache() {
    rm -f "$CONFIG_DIR/webui_font_list.json" "$CONFIG_DIR/webui_font_list.key" \
          "$CONFIG_DIR/.webui_families."* "$MODULE_DIR/.font_switch.lock" 2>/dev/null || true
    rm -rf "$MODULE_DIR/webroot/fonts" "$MODULE_DIR/webroot/emoji" 2>/dev/null || true
    mkdir -p "$MODULE_DIR/webroot/fonts" "$MODULE_DIR/webroot/emoji" 2>/dev/null || true
    chmod 755 "$MODULE_DIR/webroot" "$MODULE_DIR/webroot/fonts" "$MODULE_DIR/webroot/emoji" 2>/dev/null || true
    printf '{"status":"ok","message":"模块缓存已清理；请返回后重新刷新字体库"}\n'
}

repair_permissions() {
    chmod 755 "$MODULE_DIR" "$MODULE_DIR/common" "$MODULE_DIR/webroot" 2>/dev/null || true
    find "$MODULE_DIR/common" -maxdepth 1 -type f -exec chmod 755 {} \; 2>/dev/null || true
    find "$MODULE_DIR" -maxdepth 1 -type f -name '*.sh' -exec chmod 755 {} \; 2>/dev/null || true
    [ -f "$MODULE_DIR/system/bin/luoshud" ] && chmod 755 "$MODULE_DIR/system/bin/luoshud" 2>/dev/null || true
    chmod 775 "$FONTS_DIR" "$EMOJI_DIR" "$REPORT_DIR" 2>/dev/null || true
    printf '{"status":"ok","message":"脚本与公开目录权限已修复"}\n'
}

now_ms() {
    _ns=$(date +%s%N 2>/dev/null)
    case "$_ns" in *N*|'') printf '%s000' "$(date +%s 2>/dev/null || echo 0)" ;; *) printf '%s' "${_ns%??????}" ;; esac
}

scan_test() {
    if [ ! -x "$FONT_MANAGER" ]; then
        printf '{"status":"error","message":"字体管理脚本不可执行"}\n'
        return 1
    fi
    _start=$(now_ms)
    _tmp="$RECOVERY_DIR/scan_result.$$"
    sh "$FONT_MANAGER" action list refresh > "$_tmp" 2>&1
    _rc=$?
    _end=$(now_ms)
    _duration=$((_end - _start))
    [ "$_duration" -ge 0 ] 2>/dev/null || _duration=0
    _result=failed
    grep -q '"status":"ok"' "$_tmp" 2>/dev/null && _result=ok
    {
        printf 'duration_ms=%s\n' "$_duration"
        printf 'result=%s\n' "$_result"
        printf 'exit_code=%s\n' "$_rc"
        printf 'finished_at=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$LAST_SCAN.tmp" 2>/dev/null && mv -f "$LAST_SCAN.tmp" "$LAST_SCAN" 2>/dev/null
    rm -f "$_tmp" 2>/dev/null || true
    if [ "$_result" = ok ]; then
        printf '{"status":"ok","data":{"durationMs":%s},"message":"字体扫描完成"}\n' "$_duration"
    else
        printf '{"status":"error","data":{"durationMs":%s,"exitCode":%s},"message":"字体扫描失败，请生成诊断报告"}\n' "$_duration" "$_rc"
        return 1
    fi
}

rollback() {
    if [ ! -s "$PREVIOUS_STATE" ]; then
        printf '{"status":"error","message":"暂无可回滚配置；请先保存当前配置，或完成一次切换并完整重启"}\n'
        return 1
    fi
    if [ ! -x "$FONT_MANAGER" ]; then
        printf '{"status":"error","message":"字体管理脚本不可执行"}\n'
        return 1
    fi
    _font=$(read_kv "$PREVIOUS_STATE" font default)
    _emoji=$(read_kv "$PREVIOUS_STATE" emoji default)
    _weight=$(read_kv "$PREVIOUS_STATE" weight 0)
    _text_out=$(sh "$FONT_MANAGER" action switch_async "$_font" 2>&1)
    _text_ok=false; printf '%s' "$_text_out" | grep -q '"status":"ok"' && _text_ok=true
    _emoji_out=$(sh "$FONT_MANAGER" action emoji_switch_async "$_emoji" 2>&1)
    _emoji_ok=false; printf '%s' "$_emoji_out" | grep -q '"status":"ok"' && _emoji_ok=true
    _weight_ok=true
    case "$_weight" in ''|*[!0-9-]*) _weight=0 ;; esac
    sh "$FONT_MANAGER" action font_weight_set "$((400 + _weight))" >/dev/null 2>&1 || _weight_ok=false
    printf '{"status":"ok","data":{"font":"%s","emoji":"%s","weight":"%s","textStarted":%s,"emojiStarted":%s,"weightApplied":%s},"message":"已开始恢复可回滚配置；等待任务完成后请完整重启手机"}\n' \
        "$(json_escape "$_font")" "$(json_escape "$_emoji")" "$(json_escape "$_weight")" \
        "$(bool_json "$_text_ok")" "$(bool_json "$_emoji_ok")" "$(bool_json "$_weight_ok")"
}

generate_report() {
    _stamp=$(date '+%Y%m%d-%H%M%S' 2>/dev/null || echo unknown)
    _path="$REPORT_DIR/LuoShu-recovery-${_stamp}.txt"
    {
        echo 'LuoShu v13.5 Stable Hotfix2 Recovery Report'
        echo "generated_at=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
        echo "module=$MODULE_DIR"
        echo "version=$(sed -n 's/^version=//p' "$MODULE_DIR/module.prop" 2>/dev/null | head -n1)"
        echo "rom=$(detect_rom)"
        echo "android=$(prop ro.build.version.release)"
        echo "sdk=$(prop ro.build.version.sdk)"
        echo "manufacturer=$(prop ro.product.manufacturer)"
        echo "brand=$(prop ro.product.brand)"
        echo "device=$(prop ro.product.device)"
        echo "root=$(detect_root_manager)"
        echo "font_configs=$(list_font_configs)"
        echo "fonts_readable=$([ -r "$FONTS_DIR" ] && echo true || echo false)"
        echo "font_files=$(count_font_files "$FONTS_DIR")"
        echo "emoji_files=$(count_font_files "$EMOJI_DIR")"
        echo "current_font=$(state_font)"
        echo "current_emoji=$(state_emoji)"
        echo "font_weight=$(state_weight)"
        echo "snapshot_font=$(read_kv "$CURRENT_STATE" font '')"
        echo "snapshot_saved_at=$(read_kv "$CURRENT_STATE" saved_at 0)"
        echo "previous_font=$(read_kv "$PREVIOUS_STATE" font '')"
        echo "previous_saved_at=$(read_kv "$PREVIOUS_STATE" saved_at 0)"
        echo "last_scan_ms=$(read_kv "$LAST_SCAN" duration_ms 0)"
        echo "last_scan_result=$(read_kv "$LAST_SCAN" result never)"
        echo
        echo '--- module files ---'
        ls -ld "$MODULE_DIR" "$MODULE_DIR/common" "$MODULE_DIR/webroot" "$FONTS_DIR" "$EMOJI_DIR" 2>&1
        echo
        echo '--- recent log ---'
        tail -n 160 "$LOG_DIR/fontswitch.log" 2>/dev/null || true
    } > "$_path" 2>/dev/null
    if [ -s "$_path" ]; then
        printf '{"status":"ok","data":{"path":"%s"},"message":"自救报告已生成"}\n' "$(json_escape "$_path")"
    else
        printf '{"status":"error","message":"自救报告生成失败"}\n'
        return 1
    fi
}

case "${1:-status}" in
    status) status_json ;;
    boot_snapshot|snapshot) boot_snapshot ;;
    save_snapshot|manual_snapshot) manual_snapshot ;;
    clear_cache) clear_cache ;;
    repair_permissions) repair_permissions ;;
    scan_test|rebuild_index) clear_cache >/dev/null 2>&1; scan_test ;;
    rollback) rollback ;;
    report) generate_report ;;
    rom) save_rom_profile; status_json ;;
    *) printf '{"status":"error","message":"未知自救命令"}\n'; exit 2 ;;
esac
