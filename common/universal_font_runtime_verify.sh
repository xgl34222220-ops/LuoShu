#!/system/bin/sh
# Phase 8 universal runtime verification bridge.
# Finite, boot-scoped verification only; no resident watcher and no target discovery.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
CONFIG_DIR="${CONFIG_DIR:-$MODDIR/config}"
VERIFIER="$MODDIR/common/universal_font_runtime_verify.py"
PLAN_BRIDGE="$MODDIR/common/universal_font_plan.sh"
COMPILER_BRIDGE="$MODDIR/common/universal_font_compiler.sh"
RUNTIME_CONF="$CONFIG_DIR/universal-font-runtime.conf"
MOUNT_STATE="$CONFIG_DIR/universal-font-mount.conf"
ACTIVATED_CONF="$CONFIG_DIR/universal-font-activated.conf"
CUTOVER_CONTROLLER="$MODDIR/common/universal_font_cutover.sh"
OUTPUT_JSON="$CONFIG_DIR/universal-font-runtime-verification.json"
OUTPUT_CONF="$CONFIG_DIR/universal-font-runtime-verification.conf"
LIVE_DEPLOYMENT="$MODDIR/.luoshu-payload/.luoshu-runtime/deployment/deployment.json"
LIVE_FONT_PLAN="$MODDIR/.luoshu-payload/.luoshu-runtime/deployment/font-plan.json"
LIVE_ARTIFACT_MANIFEST="$MODDIR/.luoshu-payload/.luoshu-runtime/deployment/artifact-manifest.json"
STATE_ROOT="${LUOSHU_VERIFY_STATE_ROOT:-/data/adb/luoshu/runtime-verify}"
PID_FILE="$STATE_ROOT/verify.pid"
FONT_DUMP="$STATE_ROOT/font-manager.txt"
LOG_FILE="$MODDIR/logs/universal-runtime-verify.log"
BOOT_WAIT_LIMIT="${LUOSHU_VERIFY_BOOT_WAIT_LIMIT:-180}"
POLL_SECONDS="${LUOSHU_VERIFY_POLL_SECONDS:-2}"
SETTLE_SECONDS="${LUOSHU_VERIFY_SETTLE_SECONDS:-4}"

_uvr_log() {
    mkdir -p "$MODDIR/logs" 2>/dev/null || true
    printf '[%s] [UNIVERSAL-VERIFY] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" >> "$LOG_FILE" 2>/dev/null || true
}

_uvr_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_uvr_python() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$LUOSHU_PYTHON" "$@"
        return $?
    fi
    _uvr_root="$MODDIR/common/python"
    _uvr_bin="$_uvr_root/bin/luoshu-python"
    [ -x "$_uvr_bin" ] || return 127
    PYTHONHOME="$_uvr_root" \
    PYTHONPATH="$MODDIR/common:$_uvr_root/lib/python3.14:$_uvr_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_uvr_root/lib:$_uvr_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_uvr_bin" "$@"
}

_uvr_boot_id() {
    _uvr_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_uvr_boot" ] || _uvr_boot="$(date +%s 2>/dev/null || echo 0)-$$"
    printf '%s\n' "$_uvr_boot"
}

_uvr_boot_completed() {
    [ "${LUOSHU_VERIFY_BOOT_COMPLETED:-}" = 1 ] && return 0
    [ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ]
}

_uvr_wait_boot() {
    _uvr_waited=0
    while ! _uvr_boot_completed && [ "$_uvr_waited" -lt "$BOOT_WAIT_LIMIT" ]; do
        sleep "$POLL_SECONDS"
        _uvr_waited=$((_uvr_waited + POLL_SECONDS))
    done
    _uvr_boot_completed
}

_uvr_family() {
    _uvr_font=$(_uvr_value "$RUNTIME_CONF" font)
    [ -n "$_uvr_font" ] || _uvr_font=$(head -n1 "$CONFIG_DIR/active_font.conf" 2>/dev/null | tr -d '\r\n')
    printf '%s\n' "$_uvr_font"
}

_uvr_font_plan() {
    [ -n "${LUOSHU_VERIFY_FONT_PLAN:-}" ] && { printf '%s\n' "$LUOSHU_VERIFY_FONT_PLAN"; return 0; }
    # Phase 8 prefers the contract snapshot sealed into the active payload.
    [ -s "$LIVE_FONT_PLAN" ] && { printf '%s\n' "$LIVE_FONT_PLAN"; return 0; }
    [ -f "$PLAN_BRIDGE" ] || return 1
    MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$PLAN_BRIDGE" path "$1"
}

_uvr_artifacts() {
    [ -n "${LUOSHU_VERIFY_ARTIFACT_MANIFEST:-}" ] && { printf '%s\n' "$LUOSHU_VERIFY_ARTIFACT_MANIFEST"; return 0; }
    [ -s "$LIVE_ARTIFACT_MANIFEST" ] && { printf '%s\n' "$LIVE_ARTIFACT_MANIFEST"; return 0; }
    [ -f "$COMPILER_BRIDGE" ] || return 1
    MODDIR="$MODDIR" CONFIG_DIR="$CONFIG_DIR" sh "$COMPILER_BRIDGE" manifest "$1"
}

_uvr_deployment() {
    [ -n "${LUOSHU_VERIFY_DEPLOYMENT:-}" ] && { printf '%s\n' "$LUOSHU_VERIFY_DEPLOYMENT"; return 0; }
    printf '%s\n' "$LIVE_DEPLOYMENT"
}

_uvr_mountinfo() {
    [ -n "${LUOSHU_VERIFY_MOUNTINFO:-}" ] && { printf '%s\n' "$LUOSHU_VERIFY_MOUNTINFO"; return 0; }
    printf '/proc/self/mountinfo\n'
}

_uvr_collect_font_dump() {
    mkdir -p "$STATE_ROOT" 2>/dev/null || return 1
    if [ -n "${LUOSHU_VERIFY_FONT_DUMP:-}" ] && [ -f "$LUOSHU_VERIFY_FONT_DUMP" ]; then
        cp -f "$LUOSHU_VERIFY_FONT_DUMP" "$FONT_DUMP" 2>/dev/null || return 1
        return 0
    fi
    : > "$FONT_DUMP" 2>/dev/null || return 1
    for _uvr_cmd in "cmd font dump" "cmd font list" "dumpsys font" "dumpsys font_manager"; do
        _uvr_tmp="$STATE_ROOT/font-manager.tmp.$$"
        sh -c "$_uvr_cmd" > "$_uvr_tmp" 2>/dev/null
        if [ -s "$_uvr_tmp" ]; then
            mv -f "$_uvr_tmp" "$FONT_DUMP" 2>/dev/null || true
            return 0
        fi
        rm -f "$_uvr_tmp" 2>/dev/null || true
    done
    return 0
}

_uvr_terminal_failure() {
    _uvr_reason="$1"
    _uvr_font="$2"
    _uvr_boot="$3"
    mkdir -p "$CONFIG_DIR" 2>/dev/null || true
    # Never let a JSON result from the previous boot outrank this terminal
    # failure in the status command.
    rm -f "$OUTPUT_JSON" 2>/dev/null || true
    {
        printf 'schema=universal-font-runtime-verification-v1\n'
        printf 'grade=FAIL\n'
        printf 'state=fail\n'
        printf 'mode=universal-runtime\n'
        printf 'reason=%s\n' "$_uvr_reason"
        printf 'activeFont=%s\n' "$_uvr_font"
        printf 'deploymentId=%s\n' "$(_uvr_value "$RUNTIME_CONF" deploymentId)"
        printf 'payloadDigest=%s\n' "$(_uvr_value "$RUNTIME_CONF" payloadDigest)"
        printf 'bootId=%s\n' "$_uvr_boot"
        printf 'failureCount=1\n'
        printf 'warningCount=0\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$OUTPUT_CONF.tmp.$$" 2>/dev/null && mv -f "$OUTPUT_CONF.tmp.$$" "$OUTPUT_CONF" 2>/dev/null || true
    chmod 0644 "$OUTPUT_CONF" 2>/dev/null || true
    _uvr_log "FAIL reason=$_uvr_reason font=$_uvr_font"
    [ -f "$CUTOVER_CONTROLLER" ] && MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
        sh "$CUTOVER_CONTROLLER" rollback-from-fail "$_uvr_boot" >> "$LOG_FILE" 2>&1 || true
}

_uvr_cleanup_retired_on_pass() {
    [ "$(_uvr_value "$OUTPUT_CONF" grade)" = PASS ] || return 0
    _uvr_retired=$(_uvr_value "$ACTIVATED_CONF" retired)
    case "$_uvr_retired" in
        "$MODDIR"/.luoshu-retired/universal-*)
            rm -rf "$_uvr_retired" 2>/dev/null || return 1
            rmdir "$MODDIR/.luoshu-retired" 2>/dev/null || true
            _uvr_log "PASS retired payload released: $_uvr_retired"
            ;;
    esac
    return 0
}

_uvr_run() {
    mkdir -p "$STATE_ROOT" "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
    _uvr_boot=$(_uvr_boot_id)
    _uvr_font=$(_uvr_family)
    [ -n "$_uvr_font" ] || _uvr_font=unknown

    if ! _uvr_wait_boot; then
        _uvr_terminal_failure boot-not-completed "$_uvr_font" "$_uvr_boot"
        rm -f "$PID_FILE" 2>/dev/null || true
        return 1
    fi
    [ "$SETTLE_SECONDS" -eq 0 ] 2>/dev/null || sleep "$SETTLE_SECONDS"

    _uvr_plan=$(_uvr_font_plan "$_uvr_font")
    _uvr_artifacts=$(_uvr_artifacts "$_uvr_font")
    _uvr_deployment=$(_uvr_deployment)
    _uvr_mountinfo=$(_uvr_mountinfo)

    [ -s "$_uvr_plan" ] || { _uvr_terminal_failure fontplan-missing "$_uvr_font" "$_uvr_boot"; rm -f "$PID_FILE"; return 1; }
    [ -s "$_uvr_artifacts" ] || { _uvr_terminal_failure artifact-manifest-missing "$_uvr_font" "$_uvr_boot"; rm -f "$PID_FILE"; return 1; }
    [ -s "$_uvr_deployment" ] || { _uvr_terminal_failure deployment-missing "$_uvr_font" "$_uvr_boot"; rm -f "$PID_FILE"; return 1; }
    [ -s "$RUNTIME_CONF" ] || { _uvr_terminal_failure runtime-state-missing "$_uvr_font" "$_uvr_boot"; rm -f "$PID_FILE"; return 1; }

    _uvr_collect_font_dump || true
    # A crashed interpreter must never leave an earlier successful result usable.
    rm -f "$OUTPUT_JSON" "$OUTPUT_CONF" 2>/dev/null || true
    if [ -n "${LUOSHU_VERIFY_VISIBLE_ROOT:-}" ]; then
        _uvr_python "$VERIFIER" \
            --font-plan "$_uvr_plan" \
            --artifact-manifest "$_uvr_artifacts" \
            --deployment "$_uvr_deployment" \
            --runtime-conf "$RUNTIME_CONF" \
            --mount-state "$MOUNT_STATE" \
            --font-dump "$FONT_DUMP" \
            --mountinfo "$_uvr_mountinfo" \
            --visible-root "$LUOSHU_VERIFY_VISIBLE_ROOT" \
            --active-font "$_uvr_font" \
            --boot-id "$_uvr_boot" \
            --output-json "$OUTPUT_JSON" \
            --output-conf "$OUTPUT_CONF"
    else
        _uvr_python "$VERIFIER" \
            --font-plan "$_uvr_plan" \
            --artifact-manifest "$_uvr_artifacts" \
            --deployment "$_uvr_deployment" \
            --runtime-conf "$RUNTIME_CONF" \
            --mount-state "$MOUNT_STATE" \
            --font-dump "$FONT_DUMP" \
            --mountinfo "$_uvr_mountinfo" \
            --active-font "$_uvr_font" \
            --boot-id "$_uvr_boot" \
            --output-json "$OUTPUT_JSON" \
            --output-conf "$OUTPUT_CONF"
    fi
    _uvr_rc=$?
    if [ "$_uvr_rc" -gt 2 ]; then
        _uvr_terminal_failure verifier-execution-failed "$_uvr_font" "$_uvr_boot"
        rm -f "$PID_FILE" 2>/dev/null || true
        return 1
    fi
    if [ "$(_uvr_value "$OUTPUT_CONF" bootId)" != "$_uvr_boot" ] ||
       [ "$(_uvr_value "$OUTPUT_CONF" activeFont)" != "$_uvr_font" ] ||
       [ "$(_uvr_value "$OUTPUT_CONF" deploymentId)" != "$(_uvr_value "$RUNTIME_CONF" deploymentId)" ] ||
       [ "$(_uvr_value "$OUTPUT_CONF" payloadDigest)" != "$(_uvr_value "$RUNTIME_CONF" payloadDigest)" ]; then
        _uvr_terminal_failure verifier-result-identity-mismatch "$_uvr_font" "$_uvr_boot"
        rm -f "$PID_FILE" 2>/dev/null || true
        return 1
    fi
    _uvr_grade=$(_uvr_value "$OUTPUT_CONF" grade)
    case "$_uvr_rc:$_uvr_grade" in
        0:PASS|2:WARN|1:FAIL) ;;
        *) _uvr_terminal_failure verifier-execution-failed "$_uvr_font" "$_uvr_boot"; rm -f "$PID_FILE"; return 1 ;;
    esac
    _uvr_reason=$(_uvr_value "$OUTPUT_CONF" reason)
    _uvr_log "result=${_uvr_grade:-FAIL} reason=${_uvr_reason:-unknown} font=$_uvr_font rc=$_uvr_rc"

    if [ "$_uvr_grade" = PASS ] && [ "$_uvr_rc" -eq 0 ]; then
        _uvr_cleanup_retired_on_pass
    elif [ "$_uvr_grade" = FAIL ] && [ -f "$CUTOVER_CONTROLLER" ]; then
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
            sh "$CUTOVER_CONTROLLER" rollback-from-fail "$_uvr_boot" >> "$LOG_FILE" 2>&1 || true
    fi
    rm -f "$PID_FILE" 2>/dev/null || true
    return "$_uvr_rc"
}

_uvr_schedule() {
    mkdir -p "$STATE_ROOT" "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || true
    _uvr_boot=$(_uvr_boot_id)
    if [ -s "$OUTPUT_CONF" ] && [ "$(_uvr_value "$OUTPUT_CONF" bootId)" = "$_uvr_boot" ]; then
        case "$(_uvr_value "$OUTPUT_CONF" grade)" in PASS|WARN|FAIL) return 0 ;; esac
    fi
    if [ -s "$PID_FILE" ] && [ "$(cat "$PID_FILE.boot" 2>/dev/null)" = "$_uvr_boot" ]; then
        _uvr_pid=$(head -n1 "$PID_FILE" 2>/dev/null)
        case "$_uvr_pid" in
            ''|*[!0-9]*) ;;
            *) kill -0 "$_uvr_pid" 2>/dev/null && return 0 ;;
        esac
    fi
    ( trap '' HUP; exec sh "$0" run ) </dev/null >> "$LOG_FILE" 2>&1 &
    _uvr_pid=$!
    printf '%s\n' "$_uvr_pid" > "$PID_FILE" 2>/dev/null || true
    printf '%s\n' "$_uvr_boot" > "$PID_FILE.boot" 2>/dev/null || true
    return 0
}

case "${1:-schedule}" in
    schedule) _uvr_schedule ;;
    run) _uvr_run ;;
    status)
        if [ -s "$OUTPUT_JSON" ]; then cat "$OUTPUT_JSON"
        elif [ -s "$OUTPUT_CONF" ]; then cat "$OUTPUT_CONF"
        else printf '{"status":"pending","message":"Phase 8 runtime verification has not run"}\n'
        fi
        ;;
    *) echo "Usage: $0 {schedule|run|status}" >&2; exit 2 ;;
esac
