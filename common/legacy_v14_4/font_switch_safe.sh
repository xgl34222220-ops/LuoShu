#!/system/bin/sh
# LuoShu safe physical font switch core.
# Foreground switching never renames, deletes or rewrites the payload used by the
# current Android boot. It builds .luoshu-payload-next off-line; post-fs-data activates
# that tree before LuoShu mounts fonts on the following complete boot.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/../.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
LEGACY_DIR="$MODDIR/common/legacy_v14_4"
USER_ROOT="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$USER_ROOT/fonts"
LIVE_PAYLOAD="$MODDIR/.luoshu-payload"
STAGE_PAYLOAD="$MODDIR/.luoshu-payload-stage.$$"
NEXT_PAYLOAD="$MODDIR/.luoshu-payload-next"
NEXT_STATE="$CONFIG_DIR/font-payload-next.conf"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
LEGACY_MODE_CONF="$CONFIG_DIR/font_runtime_legacy_v14_4.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOG_FILE="$MODDIR/logs/fontswitch.log"
SWITCH_LOCK="$MODDIR/.font_switch.lock"
PROGRESS_FILE="${LUOSHU_SWITCH_PROGRESS_FILE:-}"
LOCK_HELD=false

export MODULE_DIR LUOSHU_PUBLIC_DIR="$USER_ROOT"
[ -f "$LEGACY_DIR/util_functions.sh" ] && . "$LEGACY_DIR/util_functions.sh"
[ -f "$LEGACY_DIR/font_check.sh" ] && . "$LEGACY_DIR/font_check.sh"
[ -f "$LEGACY_DIR/rom_adapters.sh" ] && . "$LEGACY_DIR/rom_adapters.sh"
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
HYPEROS_COMPAT="$LEGACY_DIR/hyperos_full_coverage.sh"
[ -f "$HYPEROS_COMPAT" ] && . "$HYPEROS_COMPAT"

type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos
mkdir -p "$CONFIG_DIR" "$MODDIR/logs" "$USER_FONTS_DIR" 2>/dev/null || true

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_state_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

progress() {
    _p="$1"; shift; _m="$*"
    [ -n "$PROGRESS_FILE" ] || return 0
    _tmp="${PROGRESS_FILE}.tmp.$$"
    {
        printf 'percent=%s\n' "$_p"
        printf 'message=%s\n' "$_m"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$PROGRESS_FILE" 2>/dev/null || true
    chmod 0644 "$PROGRESS_FILE" 2>/dev/null || true
}

safe_error() {
    progress 100 "$1"
    printf '{"status":"error","message":"%s","pipeline":"next-boot-stage"}\n' "$(json_escape "$1")"
    return 1
}

lock_cleanup() {
    [ "$LOCK_HELD" = true ] || return 0
    if type luoshu_font_lock_release >/dev/null 2>&1; then
        luoshu_font_lock_release "$SWITCH_LOCK" "$$" >/dev/null 2>&1 || \
            luoshu_font_lock_force_clear "$SWITCH_LOCK" "$$" >/dev/null 2>&1 || true
    fi
    LOCK_HELD=false
}

lock_acquire() {
    type luoshu_font_lock_acquire >/dev/null 2>&1 || { safe_error '缺少字体切换身份锁'; return 1; }
    luoshu_font_lock_acquire "$SWITCH_LOCK" "$$"
    _rc=$?
    case "$_rc" in
        0) LOCK_HELD=true; return 0 ;;
        2) safe_error '字体正在切换中，请稍后再试'; return 1 ;;
        *) safe_error '无法创建字体切换锁'; return 1 ;;
    esac
}

cleanup_stage() {
    rm -rf "$STAGE_PAYLOAD" 2>/dev/null || true
}

trap 'cleanup_stage; lock_cleanup' EXIT
trap 'cleanup_stage; lock_cleanup; exit 129' HUP
trap 'cleanup_stage; lock_cleanup; exit 130' INT
trap 'cleanup_stage; lock_cleanup; exit 143' TERM

find_text_font_file() {
    _wanted="$1"
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _family="$(detect_font_family "$(basename "$_file")")"
        else
            _family="${_file##*/}"; _family="${_family%.*}"
        fi
        case "$_family" in SysFont*|SysSans*) continue ;; esac
        [ "$_family" = "$_wanted" ] && { printf '%s\n' "$_file"; return 0; }
    done
    return 1
}

validate_global() {
    _file="$1"
    if type font_validate >/dev/null 2>&1; then
        font_validate "$_file" text || return 1
    fi
    _python="$MODDIR/common/python/bin/luoshu-python"
    _checker="$LEGACY_DIR/font_coverage.py"
    [ -x "$_python" ] && [ -f "$_checker" ] || return 0
    _pyroot="$MODDIR/common/python"
    _coverage=$(PYTHONHOME="$_pyroot" \
        PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" "$_checker" --brief "$_file" 2>/dev/null)
    _rc=$?
    [ "$_rc" -eq 0 ] && return 0
    FONT_CHECK_ERROR="${_coverage:-字体缺少全局替换所需字形}"
    return 1
}

stage_clone_live() {
    [ -d "$LIVE_PAYLOAD" ] || { safe_error '私有字体负载不存在，请重新刷入当前洛书版本'; return 1; }
    cleanup_stage
    mkdir -p "$STAGE_PAYLOAD" 2>/dev/null || return 1
    cp -al "$LIVE_PAYLOAD/." "$STAGE_PAYLOAD/" 2>/dev/null || \
        cp -af "$LIVE_PAYLOAD/." "$STAGE_PAYLOAD/" 2>/dev/null || \
        cp -rfp "$LIVE_PAYLOAD/." "$STAGE_PAYLOAD/" 2>/dev/null || return 1
    return 0
}

stage_clear_text_payload() {
    for _part in system system_ext product vendor odm oem my_product mi_ext \
                 oplus_product hw_product cust; do
        rm -rf "$STAGE_PAYLOAD/$_part/fonts" 2>/dev/null || true
        _etc="$STAGE_PAYLOAD/$_part/etc"
        [ -d "$_etc" ] || continue
        rm -f "$_etc/fonts.xml" "$_etc/font_fallback.xml" \
              "$_etc/fonts_customization.xml" "$_etc/font_customization.xml" 2>/dev/null || true
        for _xml in "$_etc"/*.xml; do
            [ -f "$_xml" ] || continue
            grep -a -qE 'LuoShuSlot-|LuoShu-|luoshu' "$_xml" 2>/dev/null && rm -f "$_xml" 2>/dev/null || true
        done
    done
    mkdir -p "$STAGE_PAYLOAD/system/fonts" 2>/dev/null || return 1
}

mirror_existing_targets() {
    _system_fonts="$STAGE_PAYLOAD/system/fonts"
    for _src in "$_system_fonts"/*; do
        [ -f "$_src" ] || continue
        _base="${_src##*/}"
        case "$_base" in *.ttf|*.otf|*.ttc) ;; *) continue ;; esac
        for _part in system_ext product vendor odm oem my_product mi_ext \
                     oplus_product hw_product cust; do
            [ -e "/$_part/fonts/$_base" ] || continue
            _dest="$STAGE_PAYLOAD/$_part/fonts/$_base"
            mkdir -p "${_dest%/*}" 2>/dev/null || continue
            if type link_or_copy_font >/dev/null 2>&1; then
                link_or_copy_font "$_src" "$_dest" >/dev/null 2>&1 || true
            else
                ln "$_src" "$_dest" 2>/dev/null || cp -f "$_src" "$_dest" 2>/dev/null || true
                chmod 0644 "$_dest" 2>/dev/null || true
            fi
        done
    done
}

stage_hyperos_complete() {
    [ "${IS_HYPEROS:-false}" = true ] || return 0
    type luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 || return 0
    LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT="$STAGE_PAYLOAD"
    export LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT
    luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 || true
    unset LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT 2>/dev/null || true
}

stage_verify() {
    _font="$1"
    [ "$_font" = default ] && return 0
    _count=$(find "$STAGE_PAYLOAD" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
        2>/dev/null | wc -l | tr -d '[:space:]')
    case "$_count" in ''|*[!0-9]*) _count=0 ;; esac
    [ "$_count" -gt 0 ] || return 1
    [ -s "$STAGE_PAYLOAD/system/fonts/.luoshu-font-store/regular.font" ] || \
        find "$STAGE_PAYLOAD/system/fonts" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
            -print -quit 2>/dev/null | grep -q .
}

resolve_previous_state() {
    PREVIOUS_FONT=$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')
    [ -n "$PREVIOUS_FONT" ] || PREVIOUS_FONT=default
    PREVIOUS_LEGACY=false
    [ -f "$LEGACY_MODE_CONF" ] && PREVIOUS_LEGACY=true
    if [ -s "$NEXT_STATE" ]; then
        _queued_previous=$(read_state_value "$NEXT_STATE" previousFont)
        _queued_legacy=$(read_state_value "$NEXT_STATE" previousLegacy)
        [ -n "$_queued_previous" ] && PREVIOUS_FONT="$_queued_previous"
        [ "$_queued_legacy" = true ] && PREVIOUS_LEGACY=true || PREVIOUS_LEGACY=false
    fi
}

prepare_next_payload() {
    _font="$1"; _previous="$2"; _previous_legacy="$3"
    _next_tmp="${NEXT_STATE}.tmp.$$"
    rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
    rm -f "$NEXT_STATE" 2>/dev/null || true
    if ! mv "$STAGE_PAYLOAD" "$NEXT_PAYLOAD" 2>/dev/null; then
        return 1
    fi
    STAGE_PAYLOAD="$MODDIR/.luoshu-payload-stage.committed.$$"
    {
        printf 'state=prepared\n'
        printf 'font=%s\n' "$_font"
        printf 'previousFont=%s\n' "$_previous"
        printf 'previousLegacy=%s\n' "$_previous_legacy"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_next_tmp" 2>/dev/null || {
        rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
        return 1
    }
    mv -f "$_next_tmp" "$NEXT_STATE" 2>/dev/null || {
        rm -rf "$NEXT_PAYLOAD" "$_next_tmp" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$NEXT_STATE" 2>/dev/null || true
    return 0
}

cancel_next_payload() {
    rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
    rm -f "$NEXT_STATE" 2>/dev/null || true
}

write_runtime_state() {
    _font="$1"
    _tmp_active="${ACTIVE_FONT_CONF}.tmp.$$"
    printf '%s\n' "$_font" > "$_tmp_active" 2>/dev/null && mv -f "$_tmp_active" "$ACTIVE_FONT_CONF" 2>/dev/null || return 1
    chmod 0644 "$ACTIVE_FONT_CONF" 2>/dev/null || true
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    {
        printf 'font=%s\n' "$_font"
        printf 'reason=next-boot-payload-prepared\n'
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    chmod 0644 "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true

    rm -f "$CONFIG_DIR/font-payload-rebuild-pending.conf" \
          "$CONFIG_DIR/font-payload-reapply-notified.conf" \
          "$CONFIG_DIR/device-font-cache-pending.conf" \
          "$CONFIG_DIR/device-font-engine.conf" \
          "$CONFIG_DIR/device-font-installed.conf" \
          "$CONFIG_DIR/device-font-dynamic-mount.conf" \
          "$CONFIG_DIR/device-font-load-verification.json" \
          "$CONFIG_DIR/native_font_index.json" "$CONFIG_DIR/native_font_index.key" \
          "$CONFIG_DIR/webui_font_list.json" "$CONFIG_DIR/webui_font_list.key" 2>/dev/null || true
    return 0
}

switch_font() {
    _font="$1"
    [ -n "$_font" ] || { safe_error '未指定字体'; return 1; }
    progress 4 '正在获取字体切换锁'
    lock_acquire || return 1
    resolve_previous_state

    _source=''
    if [ "$_font" != default ]; then
        progress 10 '正在查找并校验字体文件'
        _source="$(find_text_font_file "$_font")"
        [ -f "$_source" ] || { safe_error "字体 $_font 不存在"; return 1; }
        if ! validate_global "$_source"; then
            safe_error "${FONT_CHECK_ERROR:-字体校验失败}"
            return 1
        fi
    fi

    progress 22 '正在复制当前启动负载到安全暂存区'
    stage_clone_live || { safe_error '无法创建下一启动字体负载'; return 1; }
    progress 34 '正在清理暂存区旧文字映射'
    stage_clear_text_payload || { safe_error '无法准备下一启动字体负载'; return 1; }

    if [ "$_font" != default ]; then
        PAYLOAD_ROOT="$STAGE_PAYLOAD"
        SYSTEM_FONTS_DIR="$STAGE_PAYLOAD/system/fonts"
        export PAYLOAD_ROOT SYSTEM_FONTS_DIR
        progress 48 '正在生成 ROM 核心字体映射'
        type apply_font_by_rom >/dev/null 2>&1 || { safe_error '缺少 ROM 字体映射器'; return 1; }
        if ! apply_font_by_rom "$_source" "$SYSTEM_FONTS_DIR" quick "$_font" >> "$LOG_FILE" 2>&1; then
            safe_error 'ROM 字体映射失败，当前启动字体未被改动'
            return 1
        fi
        progress 66 '正在补齐系统分区同名字体槽位'
        mirror_existing_targets
        if [ "${IS_HYPEROS:-false}" = true ]; then
            progress 76 '正在补齐 HyperOS 状态栏、锁屏和系统 UI 字体槽位'
            stage_hyperos_complete
        fi
        progress 86 '正在校验下一启动字体负载'
        stage_verify "$_font" || { safe_error '新字体负载校验失败，当前启动字体未被改动'; return 1; }
    fi

    progress 94 '正在提交下一启动字体负载'
    prepare_next_payload "$_font" "$PREVIOUS_FONT" "$PREVIOUS_LEGACY" || {
        safe_error '下一启动字体负载提交失败，当前启动字体未被改动'
        return 1
    }
    progress 98 '正在保存字体选择状态'
    if ! write_runtime_state "$_font"; then
        cancel_next_payload
        safe_error '字体状态保存失败，下一启动负载已取消'
        return 1
    fi

    printf '%s\n' "$_font" > "$CONFIG_DIR/last_switch_result.conf" 2>/dev/null || true
    date '+%Y-%m-%d %H:%M:%S' > "$CONFIG_DIR/last_switch_time.conf" 2>/dev/null || true
    progress 100 '字体已准备完成，完整重启后生效'
    printf '{"status":"ok","data":{"font":"%s","rebootRequired":true,"core":"physical-safe-v1","pipeline":"next-boot-stage"}}\n' \
        "$(json_escape "$_font")"
    return 0
}

case "${1:-}" in
    action)
        case "${2:-}" in
            switch) switch_font "${3:-}"; exit $? ;;
            *) safe_error '安全切换核心只接管字体应用动作'; exit 2 ;;
        esac
        ;;
    *) safe_error '无效的字体切换命令'; exit 2 ;;
esac