#!/system/bin/sh
# 洛书 v14.1：事务式文字字体切换引擎。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
CONFIG_DIR="$MODDIR/config"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
TASK_FILE="$CONFIG_DIR/switch_task.conf"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOCK_FILE="$MODDIR/.font_switch.lock"
LOG_FILE="$MODDIR/logs/fontswitch.log"

for _lib in util_functions.sh font_check.sh rom_adapters.sh mount_compat.sh font_transaction.sh; do
    [ -f "$MODDIR/common/$_lib" ] && . "$MODDIR/common/$_lib"
done
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos

json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
write_task(){
    _task="$1"; _state="$2"; _font="$3"; _message="$4"; _started="$5"; _finished="$6"; _tmp="$TASK_FILE.tmp.$$"
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    {
        printf 'task=%s\n' "$_task"; printf 'state=%s\n' "$_state"; printf 'font=%s\n' "$_font"
        printf 'message=%s\n' "$_message"; printf 'started=%s\n' "$_started"; printf 'finished=%s\n' "$_finished"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}
find_font(){
    _want="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _fam=$(detect_font_family "$(basename "$_f")")
        [ "$_fam" = "$_want" ] && { printf '%s\n' "$_f"; return 0; }
    done
    return 1
}

sync_coloros_secondary(){
    [ "${IS_COLOROS:-false}" = true ] || return 0
    mkdir -p "$MODDIR/system_ext/fonts" "$MODDIR/product/fonts" 2>/dev/null || true
    rm -rf "$MODDIR/system_ext/fonts/.luoshu-font-store" "$MODDIR/product/fonts/.luoshu-font-store" 2>/dev/null || true
    for _src in "$MODDIR/system/fonts"/*; do
        [ -f "$_src" ] || continue
        _file=$(basename "$_src")
        [ -e "/system_ext/fonts/$_file" ] && link_or_copy_font "$_src" "$MODDIR/system_ext/fonts/$_file" 2>/dev/null || true
        [ -e "/product/fonts/$_file" ] && link_or_copy_font "$_src" "$MODDIR/product/fonts/$_file" 2>/dev/null || true
    done
}

apply_font_transaction(){
    _font="$1"
    if [ -e "$LOCK_FILE" ]; then
        _pid=$(cat "$LOCK_FILE" 2>/dev/null)
        [ -n "$_pid" ] && kill -0 "$_pid" 2>/dev/null && { echo '错误：字体正在切换中' >&2; return 2; }
        rm -f "$LOCK_FILE" 2>/dev/null || true
    fi
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { echo '错误：本次开机已更改文字字体，请先重启手机' >&2; return 3; }
    echo $$ > "$LOCK_FILE"; trap 'rm -f "$LOCK_FILE" 2>/dev/null; luoshu_txn_abort' EXIT HUP INT TERM

    _src=""
    if [ "$_font" != default ]; then
        _src=$(find_font "$_font")
        [ -f "$_src" ] || { echo "错误：找不到字体 $_font" >&2; return 4; }
        if type font_validate >/dev/null 2>&1 && ! font_validate "$_src" text; then echo "错误：$FONT_CHECK_ERROR" >&2; return 4; fi
    fi

    luoshu_txn_begin text || return 5
    if [ "$_font" != default ]; then
        apply_font_by_rom "$_src" "$LUOSHU_TXN_FONTS" quick "$_font" || { echo '错误：ROM 字体映射失败' >&2; return 5; }
    fi
    luoshu_txn_verify "$_font" || return 6
    luoshu_txn_commit || { echo '错误：无法提交字体事务，原配置已保留' >&2; return 7; }
    sync_coloros_secondary

    mkdir -p "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
    printf '%s\n' "$_font" > "$ACTIVE_FONT_CONF" 2>/dev/null || return 8
    rm -f "$CONFIG_DIR/font_mix.conf" "$CONFIG_DIR/previous_font.conf" 2>/dev/null || true
    printf 'font=%s\ntime=%s\n' "$_font" "$(date +%s)" > "$TEXT_REBOOT_REQUIRED" 2>/dev/null || return 8
    printf '%s\n' "$_font" > "$CONFIG_DIR/last_switch_result.conf" 2>/dev/null || true
    chmod 0644 "$ACTIVE_FONT_CONF" "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    type luoshu_sync_mount_payload >/dev/null 2>&1 && luoshu_sync_mount_payload 2>/dev/null || true
    rm -f "$LOCK_FILE" 2>/dev/null || true
    trap - EXIT HUP INT TERM
    return 0
}

case "${1:-status}" in
    start)
        _font="$2"; [ -n "$_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; exit 0; }
        [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; exit 0; }
        mkdir -p "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
        _task="text-$(date +%s)-$$"; _started=$(date +%s)
        write_task "$_task" running "$_font" '正在安全生成字体目录' "$_started" ''
        (
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] v14.1 switch start: $_font task=$_task" >> "$LOG_FILE" 2>/dev/null
            if MODDIR="$MODDIR" apply_font_transaction "$_font" >> "$LOG_FILE" 2>&1; then
                write_task "$_task" success "$_font" '字体已准备，完整重启后生效' "$_started" "$(date +%s)"
                command -v cmd >/dev/null 2>&1 && cmd notification post -t 洛书 luoshu-text "字体已准备，请完整重启手机。" >/dev/null 2>&1 || true
            else
                _rc=$?; write_task "$_task" failed "$_font" "切换失败（代码 $_rc），原字体配置未被破坏" "$_started" "$(date +%s)"
            fi
        ) &
        printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_task")"
        ;;
    apply) apply_font_transaction "$2" ;;
    *) printf '{"status":"error","message":"未知字体切换命令"}\n' ;;
esac
exit 0
