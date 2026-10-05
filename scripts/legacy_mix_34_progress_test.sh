#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-legacy-34)
cleanup() {
    [ ! -f "${MODULE:-}/common/task_scope.sh" ] || MODDIR="$MODULE" sh "$MODULE/common/task_scope.sh" cancel-all "$MODULE" >/dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap cleanup EXIT HUP INT TERM

MODULE="$TMP/module"
PUBLIC="$TMP/public"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/cache" "$MODULE/logs" "$PUBLIC/fonts"
cp "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh" "$MODULE/common/v142_weighted_mix.sh"
cp "$ROOT/common/background_task.sh" "$MODULE/common/background_task.sh"
cp "$ROOT/common/mix_task_handoff.sh" "$MODULE/common/mix_task_handoff.sh"
for helper in task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py; do
    cp "$ROOT/common/$helper" "$MODULE/common/$helper"
done
export LUOSHU_TASK_SCOPE_PYTHON="$(command -v python3)"
export LUOSHU_RUNTIME_PATHS_PYTHON="$LUOSHU_TASK_SCOPE_PYTHON"
printf 'id=LuoShu\n' > "$MODULE/module.prop"

cat >"$MODULE/common/util_functions.sh" <<'EOF_UTIL'
detect_font_family() { printf '%s\n' "${1%%-*}"; }
detect_font_weight() { printf 'regular\n'; }
is_variable_font() { return 1; }
EOF_UTIL

cat >"$MODULE/common/font_check.sh" <<'EOF_CHECK'
font_validate() {
    FONT_CHECK_VARIABLE=false
    FONT_CHECK_FORMAT=TTF
    FONT_CHECK_ERROR=''
    return 0
}
EOF_CHECK

# Register the nested task immediately, then deliberately keep the start shell
# alive. The public task must advance beyond 34% without waiting for this shell.
cat >"$MODULE/common/font_mix.sh" <<'EOF_ENGINE'
#!/bin/sh
MODDIR="${MODDIR:-${0%/*}/..}"
TASK="$MODDIR/config/mix_task.conf"
case "${1:-}" in
    start)
        cat >"$TASK" <<EOF_TASK
task=slow-start-inner
state=running
message=正在生成完整复合字体
cjk=$2
latin=$3
digit=$4
started=1
finished=
EOF_TASK
        sh "$MODDIR/common/task_scope.sh" run --pid-file "$MODDIR/.luoshu-state/tasks/mix_worker.pid" \
            --task slow-start-inner --timeout 12 -- sh "$0" worker "$2" "$3" "$4"
        printf '%s\n' '{"status":"ok","data":{"task":"slow-start-inner"}}'
        ;;
    worker)
        sleep 4
        cat >"$TASK" <<EOF_TASK
task=slow-start-inner
state=success
message=完整复合字体已准备
cjk=$2
latin=$3
digit=$4
started=1
finished=2
EOF_TASK
        ;;
    recover) printf '%s\n' '{"status":"ok"}' ;;
esac
EOF_ENGINE
chmod 0755 "$MODULE/common"/*.sh

printf 'font-data\n' >"$PUBLIC/fonts/CJK-Regular.ttf"
printf 'font-data\n' >"$PUBLIC/fonts/Latin-Regular.ttf"
printf 'font-data\n' >"$PUBLIC/fonts/Digit-Regular.ttf"

START=$(MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" \
    sh "$MODULE/common/v142_weighted_mix.sh" start CJK Latin Digit wght=400 wght=400 wght=400)
OUTER=$(printf '%s\n' "$START" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
test -n "$OUTER"

COUNT=0
PERCENT=0
while [ "$COUNT" -lt 3 ]; do
    PERCENT=$(sed -n 's/^percent=//p' "$MODULE/config/axes_task.conf" 2>/dev/null | head -n1)
    case "$PERCENT" in ''|*[!0-9]*) PERCENT=0 ;; esac
    [ "$PERCENT" -ge 36 ] 2>/dev/null && break
    sleep 1
    COUNT=$((COUNT + 1))
done
if [ "$PERCENT" -lt 36 ] 2>/dev/null; then
    echo "legacy composite task stayed at ${PERCENT}% while nested start was alive" >&2
    cat "$MODULE/config/axes_task.conf" >&2 2>/dev/null || true
    exit 1
fi

COUNT=0
while [ "$COUNT" -lt 10 ]; do
    STATE=$(sed -n 's/^state=//p' "$MODULE/config/axes_task.conf" 2>/dev/null | head -n1)
    [ "$STATE" = success ] && break
    sleep 1
    COUNT=$((COUNT + 1))
done
test "${STATE:-}" = success
COUNT=0
while ! MODDIR="$MODULE" sh "$MODULE/common/task_scope.sh" cleaned "$MODULE/.luoshu-state/tasks/axes_worker.pid" "$OUTER"; do
    [ "$COUNT" -lt 30 ] || exit 1
    sleep .1
    COUNT=$((COUNT + 1))
done
MODDIR="$MODULE" sh "$MODULE/common/task_scope.sh" cleaned "$MODULE/.luoshu-state/tasks/mix_worker.pid" slow-start-inner

grep -q 'background_task.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'mix_task_handoff.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'mix-engine-start' "$ROOT/common/legacy_v14_4/font_mix_runtime.sh"
! grep -q '_output=$(LUOSHU_PUBLIC_DIR=' "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
! sed -n '/^payload_stage_begin()/,/^}/p' "$ROOT/common/legacy_v14_4/font_mix_engine.sh" | grep -q 'cp -af'
grep -q 'hyperos_metrics_batch.py' "$ROOT/common/hyperos_stage_complete.sh"

# Replacing a task must also stop its old completion monitor promptly. It must
# neither poll for the former twelve-minute budget nor finalize the new task.
printf 'task=newer-task\nstate=running\n' > "$MODULE/config/mix_task.conf"
python3 - "$ROOT" "$MODULE" <<'PY'
import os
from pathlib import Path
import subprocess
import sys
root, module = map(Path, sys.argv[1:])
subprocess.run(["sh", str(root / "common/legacy_v14_4/font_mix_runtime.sh"),
                "monitor", "superseded-task"],
               env={**os.environ, "MODDIR": str(module), "LUOSHU_REAL_MODDIR": str(module)},
               check=True, timeout=3)
assert not (module / "config/mix-finalize-state.conf").exists()
PY

echo 'Legacy composite start advances past 34% before the nested start shell exits.'
