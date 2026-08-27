#!/system/bin/sh
# LuoShu v4 UI compatibility backend using the last pre-reset v14.4 font switch core.
# This path deliberately avoids the v2/v4 device-template, slot-build, XML batch and
# fast-validation payload pipeline that can stall near the end of foreground apply.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
LEGACY_DIR="$MODDIR/common/legacy_v14_4"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LEGACY_MODE_CONF="$CONFIG_DIR/font_runtime_legacy_v14_4.conf"
LOG_FILE="$MODDIR/logs/fontswitch.log"
LEGACY_SWITCH_LOCK="$MODDIR/.font_switch.lock"
LEGACY_LOCK_HELD=false

# Current releases keep the mountable tree private. Generate the old v14.4 aliases
# directly inside that source tree, then let the existing self-mount layer expose it.
if [ -d "$MODDIR/.luoshu-payload" ]; then
    PAYLOAD_ROOT="$MODDIR/.luoshu-payload"
else
    PAYLOAD_ROOT="$MODDIR"
fi
SYSTEM_FONTS_DIR="$PAYLOAD_ROOT/system/fonts"

export MODULE_DIR LUOSHU_PUBLIC_DIR
[ -f "$LEGACY_DIR/util_functions.sh" ] && . "$LEGACY_DIR/util_functions.sh"
[ -f "$LEGACY_DIR/font_check.sh" ] && . "$LEGACY_DIR/font_check.sh"
[ -f "$LEGACY_DIR/rom_adapters.sh" ] && . "$LEGACY_DIR/rom_adapters.sh"
# Only concurrency safety is shared with v4. Font mapping, validation and payload
# generation above remain the isolated v14.4 implementation.
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"

type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos
mkdir -p "$CONFIG_DIR" "$MODDIR/logs" "$SYSTEM_FONTS_DIR" "$USER_FONTS_DIR" 2>/dev/null || true

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

legacy_error() {
    _msg="$(json_escape "$1")"
    printf '{"status":"error","message":"%s","legacyCore":"v14.4.0"}\n' "$_msg"
    return 1
}

legacy_lock_cleanup() {
    [ "$LEGACY_LOCK_HELD" = true ] || return 0
    if type luoshu_font_lock_release >/dev/null 2>&1; then
        luoshu_font_lock_release "$LEGACY_SWITCH_LOCK" "$$" >/dev/null 2>&1 || \
            luoshu_font_lock_force_clear "$LEGACY_SWITCH_LOCK" "$$" >/dev/null 2>&1 || true
    fi
    LEGACY_LOCK_HELD=false
}

legacy_lock_acquire() {
    type luoshu_font_lock_acquire >/dev/null 2>&1 || {
        legacy_error '缺少字体切换身份锁'
        return 1
    }
    luoshu_font_lock_acquire "$LEGACY_SWITCH_LOCK" "$$"
    _legacy_lock_rc=$?
    case "$_legacy_lock_rc" in
        0)
            LEGACY_LOCK_HELD=true
            return 0
            ;;
        2)
            legacy_error '字体正在切换中，请稍后再试'
            return 1
            ;;
        *)
            legacy_error '无法创建字体切换锁'
            return 1
            ;;
    esac
}

trap 'legacy_lock_cleanup' EXIT
trap 'legacy_lock_cleanup; exit 129' HUP
trap 'legacy_lock_cleanup; exit 130' INT
trap 'legacy_lock_cleanup; exit 143' TERM

legacy_find_text_font_file() {
    _wanted="$1"
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _family="$(detect_font_family "$(basename "$_file")")"
        else
            _family="${_file##*/}"
            _family="${_family%.*}"
        fi
        case "$_family" in SysFont*|SysSans*) continue ;; esac
        [ "$_family" = "$_wanted" ] && { printf '%s\n' "$_file"; return 0; }
    done
    return 1
}

# Use the original lightweight v14 validation. Keep its old coverage checker isolated
# from the current runtime so this route cannot fall back into v4 cached validation.
legacy_validate_global() {
    _file="$1"
    type font_validate >/dev/null 2>&1 || return 0
    font_validate "$_file" text || return 1

    _python="$MODDIR/common/python/bin/luoshu-python"
    _checker="$LEGACY_DIR/font_coverage.py"
    [ -x "$_python" ] && [ -f "$_checker" ] || return 0
    _pyroot="$MODDIR/common/python"
    _coverage=$(PYTHONHOME="$_pyroot" \
        PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" "$_checker" --brief "$_file" 2>/dev/null)
    _rc=$?
    if [ "$_rc" -ne 0 ]; then
        [ -n "$_coverage" ] || _coverage='字体缺少全局替换所需字形'
        FONT_CHECK_ERROR="$_coverage"
        return 1
    fi
    return 0
}

legacy_clear_generated_xml() {
    # v14.4 relies on the ROM's own family/fallback XML and replaces physical files only.
    for _part in system system_ext product vendor my_product mi_ext oplus_product; do
        _etc="$PAYLOAD_ROOT/$_part/etc"
        [ -d "$_etc" ] || continue
        rm -f "$_etc/fonts.xml" "$_etc/font_fallback.xml" \
              "$_etc/fonts_customization.xml" "$_etc/font_customization.xml" 2>/dev/null || true
        for _xml in "$_etc"/*.xml; do
            [ -f "$_xml" ] || continue
            if grep -a -qE 'LuoShuSlot-|LuoShu-|luoshu' "$_xml" 2>/dev/null; then
                rm -f "$_xml" 2>/dev/null || true
            fi
        done
    done
}

legacy_clear_payload_fonts() {
    # The private payload contains only LuoShu overlay files. Clearing these directories
    # reveals the stock lower layer; emoji/symbol/other-language fonts stay untouched.
    for _part in system system_ext product vendor my_product mi_ext oplus_product; do
        _dir="$PAYLOAD_ROOT/$_part/fonts"
        [ -d "$_dir" ] || continue
        rm -rf "$_dir" 2>/dev/null || true
    done
    mkdir -p "$SYSTEM_FONTS_DIR" 2>/dev/null || return 1
    legacy_clear_generated_xml
}

legacy_mirror_existing_partition_targets() {
    # v14.4's physical filename table is authoritative. Mirror every generated alias
    # into any additional real partition that contains the same filename so HyperOS /
    # ColorOS variants that moved Roboto/GoogleSans files still receive the old mapping.
    for _src in "$SYSTEM_FONTS_DIR"/*; do
        [ -f "$_src" ] || continue
        _base="${_src##*/}"
        case "$_base" in *.ttf|*.otf|*.ttc) ;; *) continue ;; esac
        for _part in system_ext product vendor my_product mi_ext oplus_product; do
            [ -e "/$_part/fonts/$_base" ] || continue
            _dest_dir="$PAYLOAD_ROOT/$_part/fonts"
            mkdir -p "$_dest_dir" 2>/dev/null || continue
            if type link_or_copy_font >/dev/null 2>&1; then
                link_or_copy_font "$_src" "$_dest_dir/$_base" >/dev/null 2>&1 || true
            else
                ln "$_src" "$_dest_dir/$_base" 2>/dev/null || cp -f "$_src" "$_dest_dir/$_base" 2>/dev/null || true
                chmod 0644 "$_dest_dir/$_base" 2>/dev/null || true
            fi
        done
    done
}

legacy_disable_v4_rebuild_state() {
    # Do not let a stale v4 schema marker rebuild or replace the v14.4 payload after reboot.
    rm -f \
        "$CONFIG_DIR/font-payload-rebuild-pending.conf" \
        "$CONFIG_DIR/font-payload-reapply-notified.conf" \
        "$CONFIG_DIR/device-font-cache-pending.conf" \
        "$CONFIG_DIR/device-font-engine.conf" \
        "$CONFIG_DIR/device-font-installed.conf" \
        "$CONFIG_DIR/device-font-dynamic-mount.conf" \
        "$CONFIG_DIR/device-font-load-verification.json" \
        "$CONFIG_DIR/font-runtime-targets.conf" \
        "$CONFIG_DIR/font-target-aliases.conf" \
        "$CONFIG_DIR/font-target-coverage.conf" \
        "$CONFIG_DIR/font-config-overlay.conf" 2>/dev/null || true
}

legacy_write_mode() {
    _font="$1"
    _tmp="${LEGACY_MODE_CONF}.tmp.$$"
    {
        printf 'enabled=true\n'
        printf 'core=v14.4.0\n'
        printf 'font=%s\n' "$_font"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$LEGACY_MODE_CONF" 2>/dev/null || return 1
    chmod 0600 "$LEGACY_MODE_CONF" 2>/dev/null || true
}

legacy_switch_font() {
    _font_id="$1"
    [ -n "$_font_id" ] || { legacy_error '未指定字体'; return 1; }
    legacy_lock_acquire || return 1

    _source=''
    if [ "$_font_id" != default ]; then
        _source="$(legacy_find_text_font_file "$_font_id")"
        [ -f "$_source" ] || { legacy_error "字体 $_font_id 不存在"; return 1; }
        if ! legacy_validate_global "$_source"; then
            legacy_error "${FONT_CHECK_ERROR:-字体校验失败}"
            return 1
        fi
    fi

    # Validation has succeeded: only now replace the staged overlay atomically enough for
    # the next boot. No device template, slot builder, XML batch, provider scan or v4 gate.
    legacy_clear_payload_fonts || { legacy_error '无法清理旧字体负载'; return 1; }
    legacy_disable_v4_rebuild_state

    if [ "$_font_id" = default ]; then
        rm -f "$LEGACY_MODE_CONF" 2>/dev/null || true
    else
        if ! type apply_font_by_rom >/dev/null 2>&1; then
            legacy_error '缺少 v14.4 ROM 字体映射器'
            return 1
        fi
        if ! apply_font_by_rom "$_source" "$SYSTEM_FONTS_DIR" quick "$_font_id" >> "$LOG_FILE" 2>&1; then
            legacy_clear_payload_fonts >/dev/null 2>&1 || true
            legacy_error 'v14.4 ROM 字体映射失败'
            return 1
        fi
        legacy_mirror_existing_partition_targets
        legacy_write_mode "$_font_id" || { legacy_error '无法写入 v14.4 运行模式'; return 1; }
    fi

    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF" 2>/dev/null || { legacy_error '无法保存当前字体'; return 1; }
    chmod 0644 "$ACTIVE_FONT_CONF" 2>/dev/null || true

    if [ "$_font_id" != default ]; then
        _recent="$CONFIG_DIR/recent_fonts.conf"
        _tmp="${_recent}.tmp.$$"
        {
            printf '%s\n' "$_font_id"
            [ -f "$_recent" ] && awk -v selected="$_font_id" 'NF && $0 != selected && !seen[$0]++ { print; if (++count >= 9) exit }' "$_recent"
        } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$_recent" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
    fi

    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    {
        printf 'font=%s\n' "$_font_id"
        printf 'reason=legacy-v14.4-switch\n'
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    chmod 0644 "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true

    printf '%s\n' "$_font_id" > "$CONFIG_DIR/last_switch_result.conf" 2>/dev/null || true
    date '+%Y-%m-%d %H:%M:%S' > "$CONFIG_DIR/last_switch_time.conf" 2>/dev/null || true
    rm -f "$CONFIG_DIR/native_font_index.json" "$CONFIG_DIR/native_font_index.key" \
          "$CONFIG_DIR/webui_font_list.json" "$CONFIG_DIR/webui_font_list.key" 2>/dev/null || true

    printf '{"status":"ok","data":{"font":"%s","rebootRequired":true,"legacyCore":"v14.4.0","pipeline":"physical-file-map"}}\n' "$(json_escape "$_font_id")"
    return 0
}

case "${1:-}" in
    action)
        case "${2:-}" in
            switch) legacy_switch_font "${3:-}" ; exit $? ;;
            *) legacy_error 'v14.4 后端只接管字体应用动作'; exit 2 ;;
        esac
        ;;
    *) legacy_error '无效的 v14.4 切换命令'; exit 2 ;;
esac
