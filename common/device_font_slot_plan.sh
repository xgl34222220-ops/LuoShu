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
PLAN_TIMEOUT_SECONDS="${LUOSHU_SLOT_PLAN_TIMEOUT_SECONDS:-180}"
PLAN_NICE_LEVEL="${LUOSHU_SLOT_PLAN_NICE_LEVEL:-10}"
case "$PLAN_TIMEOUT_SECONDS" in ''|*[!0-9]*) PLAN_TIMEOUT_SECONDS=180 ;; esac
[ "$PLAN_TIMEOUT_SECONDS" -ge 30 ] 2>/dev/null || PLAN_TIMEOUT_SECONDS=30
[ "$PLAN_TIMEOUT_SECONDS" -le 600 ] 2>/dev/null || PLAN_TIMEOUT_SECONDS=600
case "$PLAN_NICE_LEVEL" in ''|*[!0-9-]*) PLAN_NICE_LEVEL=10 ;; esac
[ "$PLAN_NICE_LEVEL" -ge 0 ] 2>/dev/null || PLAN_NICE_LEVEL=0
[ "$PLAN_NICE_LEVEL" -le 19 ] 2>/dev/null || PLAN_NICE_LEVEL=19

log_plan() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG" 2>/dev/null || true
}

current_boot_id() {
    _cbi=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_cbi" ] || _cbi=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    [ -n "$_cbi" ] || _cbi=unknown
    printf '%s\n' "$_cbi"
}

python_run() {
    [ -x "$PYTHON" ] && [ -f "$PLANNER" ] || return 1
    if command -v timeout >/dev/null 2>&1; then
        set -- timeout "$PLAN_TIMEOUT_SECONDS" "$PYTHON" "$PLANNER" "$@"
    elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        set -- toybox timeout "$PLAN_TIMEOUT_SECONDS" "$PYTHON" "$PLANNER" "$@"
    else
        # Android normally provides toybox timeout. The fallback still lowers priority,
        # but reports the missing hard guard in the log for diagnostics.
        log_plan "系统缺少 timeout，槽位规划无法启用硬超时"
        set -- "$PYTHON" "$PLANNER" "$@"
    fi
    if command -v nice >/dev/null 2>&1; then
        set -- nice -n "$PLAN_NICE_LEVEL" "$@"
    fi
    (
        export PYTHONHOME="$PYROOT"
        export PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        exec "$@"
    )
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

source_identity() {
    _si_path="$1"
    _si_stat=$(stat -c '%d:%i:%s:%Y:%Z' "$_si_path" 2>/dev/null)
    [ -n "$_si_stat" ] || _si_stat=$(stat -c '%s:%Y' "$_si_path" 2>/dev/null)
    [ -n "$_si_stat" ] || _si_stat=$(ls -ln "$_si_path" 2>/dev/null)
    printf '%s\n' "$_si_stat"
}

plan_key() {
    _pk_source="$1"
    _pk_source_identity=$(source_identity "$_pk_source")
    _pk_template_hash=$(file_digest "$TEMPLATE")
    printf 'slot-plan-v2|%s|%s|%s\n' "$_pk_source" "$_pk_source_identity" "$_pk_template_hash"
}

release_lock() {
    rm -rf "$LOCK" 2>/dev/null || true
}

acquire_lock() {
    _al_boot=$(current_boot_id)
    if [ -d "$LOCK" ]; then
        _al_old_boot=$(cat "$LOCK/boot_id" 2>/dev/null | tr -d '\r\n')
        _al_old_pid=$(cat "$LOCK/pid" 2>/dev/null | tr -d '\r\n')
        if [ -z "$_al_old_boot" ] || [ "$_al_old_boot" != "$_al_boot" ] || \
           [ -z "$_al_old_pid" ] || ! kill -0 "$_al_old_pid" 2>/dev/null; then
            log_plan "清理上一启动周期遗留的槽位规划锁"
            rm -rf "$LOCK" 2>/dev/null || true
        else
            log_plan "已有槽位规划任务在运行"
            return 1
        fi
    fi
    mkdir "$LOCK" 2>/dev/null || return 1
    printf '%s\n' "$_al_boot" > "$LOCK/boot_id" 2>/dev/null || true
    printf '%s\n' "$$" > "$LOCK/pid" 2>/dev/null || true
    chmod 0600 "$LOCK/boot_id" "$LOCK/pid" 2>/dev/null || true
    return 0
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

    if [ ! -s "$TEMPLATE" ] && [ -f "$TEMPLATE_HELPER" ]; then
        MODDIR="$MODDIR" sh "$TEMPLATE_HELPER" ensure >/dev/null 2>&1 || true
    fi
    [ -s "$TEMPLATE" ] || {
        log_plan "设备原厂字体模板尚未生成"
        return 2
    }

    _bp_key=$(plan_key "$_bp_source")
    _bp_old=$(head -n1 "$KEY" 2>/dev/null | tr -d '\r\n')
    if [ "$_bp_force" != 1 ] && [ -n "$_bp_key" ] && [ "$_bp_key" = "$_bp_old" ] && [ -s "$OUT" ]; then
        log_plan "字体 $_bp_font_id 的槽位计划未变化，跳过重建"
        return 0
    fi

    if ! acquire_lock; then
        return 0
    fi
    trap release_lock EXIT HUP INT TERM

    # 获取锁后再次检查，避免两个近同时启动的请求重复解析同一字体。
    _bp_old=$(head -n1 "$KEY" 2>/dev/null | tr -d '\r\n')
    if [ "$_bp_force" != 1 ] && [ -n "$_bp_key" ] && [ "$_bp_key" = "$_bp_old" ] && [ -s "$OUT" ]; then
        log_plan "字体 $_bp_font_id 的槽位计划已由另一任务更新，跳过"
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
        case "$_bp_rc" in
            124|137) log_plan "字体 $_bp_font_id 的逐槽位计划超过 ${PLAN_TIMEOUT_SECONDS} 秒，已终止" ;;
            *) log_plan "字体 $_bp_font_id 的逐槽位计划失败：code=$_bp_rc result=$_bp_result" ;;
        esac
        return 1
    fi

    chmod 0600 "$_bp_tmp" 2>/dev/null || true
    mv -f "$_bp_tmp" "$OUT" 2>/dev/null || return 1
    {
        printf '%s\n' "$_bp_key"
        printf 'font=%s\n' "$_bp_font_id"
        printf 'source=%s\n' "$_bp_source"
        printf 'bootId=%s\n' "$(current_boot_id)"
        printf 'time=%s\n' "$(date +%s)"
    } > "$KEY" 2>/dev/null || true
    chmod 0600 "$KEY" 2>/dev/null || true
    log_plan "字体 $_bp_font_id 的逐槽位计划完成：$_bp_result"
    return 0
}

clear_plan() {
    rm -f "$OUT" "$OUT.tmp" "$OUT".tmp.* "$KEY" 2>/dev/null || true
    rm -rf "$LOCK" 2>/dev/null || true
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
