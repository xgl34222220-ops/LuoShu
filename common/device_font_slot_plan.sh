#!/system/bin/sh
# LuoShu v2.2 per-device slot-plan wrapper.
# This stage is read-only with respect to Android: it creates a plan for the selected
# source font but does not change the active systemless font payload.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
PYROOT="$MODDIR/common/python"
PYTHON="$PYROOT/bin/luoshu-python"
PLANNER="$MODDIR/common/device_font_slot_plan.py"
TEMPLATE_HELPER="$MODDIR/common/device_font_template.sh"
TEMPLATE="$MODDIR/config/device-font-template.json"
OUT="$MODDIR/config/active-font-slot-plan.json"
KEY="$MODDIR/config/active-font-slot-plan.key"
LOG="$MODDIR/logs/device-font-slot-plan.log"
LOCK="$MODDIR/.device-font-slot-plan.lock"

log_plan() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG" 2>/dev/null || true
}

python_run() {
    [ -x "$PYTHON" ] && [ -f "$PLANNER" ] || return 1
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYTHON" "$PLANNER" "$@"
}

file_digest() {
    _fd_path="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$_fd_path" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$_fd_path" 2>/dev/null | awk '{print $1}'
    else
        cksum "$_fd_path" 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

plan_key() {
    _pk_source="$1"
    _pk_source_hash=$(file_digest "$_pk_source")
    _pk_template_hash=$(file_digest "$TEMPLATE")
    printf '%s|%s\n' "$_pk_source_hash" "$_pk_template_hash"
}

build_plan() {
    _bp_source="$1"
    _bp_font_id="${2:-custom}"
    _bp_force="${3:-0}"
    [ -f "$_bp_source" ] || {
        log_plan "源字体不存在：$_bp_source"
        return 1
    }
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || return 1
    if ! mkdir "$LOCK" 2>/dev/null; then
        log_plan "已有槽位规划任务在运行"
        return 0
    fi
    trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT HUP INT TERM

    if [ ! -s "$TEMPLATE" ] && [ -f "$TEMPLATE_HELPER" ]; then
        MODDIR="$MODDIR" sh "$TEMPLATE_HELPER" ensure >/dev/null 2>&1 || true
    fi
    [ -s "$TEMPLATE" ] || {
        log_plan "设备原厂字体模板尚未生成"
        return 2
    }

    _bp_key=$(plan_key "$_bp_source")
    _bp_old=$(cat "$KEY" 2>/dev/null)
    if [ "$_bp_force" != 1 ] && [ -n "$_bp_key" ] && [ "$_bp_key" = "$_bp_old" ] && [ -s "$OUT" ]; then
        log_plan "字体 $_bp_font_id 的槽位计划未变化，跳过重建"
        return 0
    fi

    _bp_tmp="$OUT.tmp.$$"
    rm -f "$_bp_tmp" 2>/dev/null || true
    _bp_result=$(python_run \
        --template "$TEMPLATE" \
        --source "$_bp_source" \
        --output "$_bp_tmp" 2>> "$LOG")
    _bp_rc=$?
    if [ "$_bp_rc" -ne 0 ] || [ ! -s "$_bp_tmp" ]; then
        rm -f "$_bp_tmp" 2>/dev/null || true
        log_plan "字体 $_bp_font_id 的逐槽位计划失败：code=$_bp_rc result=$_bp_result"
        return 1
    fi

    chmod 0600 "$_bp_tmp" 2>/dev/null || true
    mv -f "$_bp_tmp" "$OUT" 2>/dev/null || return 1
    {
        printf '%s\n' "$_bp_key"
        printf 'font=%s\n' "$_bp_font_id"
        printf 'source=%s\n' "$_bp_source"
        printf 'time=%s\n' "$(date +%s)"
    } > "$KEY" 2>/dev/null || true
    chmod 0600 "$KEY" 2>/dev/null || true
    log_plan "字体 $_bp_font_id 的逐槽位计划完成：$_bp_result"
    return 0
}

clear_plan() {
    rm -f "$OUT" "$OUT.tmp" "$KEY" 2>/dev/null || true
    rmdir "$LOCK" 2>/dev/null || true
    return 0
}

case "${1:-path}" in
    build)
        shift
        [ -n "${1:-}" ] || { echo "Usage: $0 build <source-font> [font-id]" >&2; exit 2; }
        build_plan "$1" "${2:-custom}" 0
        ;;
    refresh)
        shift
        [ -n "${1:-}" ] || { echo "Usage: $0 refresh <source-font> [font-id]" >&2; exit 2; }
        build_plan "$1" "${2:-custom}" 1
        ;;
    clear) clear_plan ;;
    path) printf '%s\n' "$OUT" ;;
    *) echo "Usage: $0 {build|refresh|clear|path}" >&2; exit 2 ;;
esac
