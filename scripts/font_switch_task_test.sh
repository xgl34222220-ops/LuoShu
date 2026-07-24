#!/bin/sh
set -e

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export MODDIR="$TMP/module"
export LUOSHU_SWITCH_TASK_FILE="$MODDIR/config/switch_task.conf"
export LUOSHU_SWITCH_LOG="$MODDIR/logs/fontswitch.log"
export LUOSHU_SWITCH_TIMEOUT_SECONDS=5
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/logs"

MANAGER="$TMP/fake-manager.sh"
cat > "$MANAGER" <<'EOF_MANAGER'
#!/bin/sh
case "${3:-}" in
    good) printf '%s\n' '{"status":"ok","data":{"font":"good"}}' ;;
    bad) printf '%s\n' '{"status":"error","message":"fake failure"}' ;;
    slow)
        trap 'printf "%s\n" rolled-back > "${ROLLBACK_MARKER:?}"; exit 143' TERM INT
        sleep 30
        printf '%s\n' '{"status":"ok"}'
        ;;
    *) printf '%s\n' '{"status":"error","message":"unknown"}' ;;
esac
EOF_MANAGER
chmod +x "$MANAGER"
export LUOSHU_FONT_MANAGER="$MANAGER"
export ROLLBACK_MARKER="$TMP/rollback"

wait_state() {
    wanted="$1"
    i=0
    state=''
    while [ "$i" -lt 120 ]; do
        state="$(sed -n 's/^state=//p' "$LUOSHU_SWITCH_TASK_FILE" 2>/dev/null | head -n1)"
        [ "$state" = "$wanted" ] && return 0
        sleep 0.1
        i=$((i + 1))
    done
    echo "timed out waiting for state=$wanted; current=${state:-missing}" >&2
    cat "$LUOSHU_SWITCH_TASK_FILE" >&2 || true
    return 1
}

start_output="$(sh "$ROOT/common/font_switch_task.sh" start good)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state success
grep -q '^message=字体已快速映射' "$LUOSHU_SWITCH_TASK_FILE"

start_output="$(sh "$ROOT/common/font_switch_task.sh" start bad)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state failed
grep -q 'fake failure' "$LUOSHU_SWITCH_TASK_FILE"

start_output="$(sh "$ROOT/common/font_switch_task.sh" start slow)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state failed
grep -q '超过 5 秒' "$LUOSHU_SWITCH_TASK_FILE"

status_output="$(sh "$ROOT/common/font_switch_task.sh" status)"
printf '%s\n' "$status_output" | grep -q '"state":"failed"'

echo 'font_switch_task_test: PASS'
