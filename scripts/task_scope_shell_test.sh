#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
MODDIR="$TMP/module"; export MODDIR
mkdir -p "$MODDIR/common"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
for part in task_scope.sh task_scope.py background_task.sh runtime_paths.sh runtime_paths_lock.py; do
    ln -s "$ROOT/common/$part" "$MODDIR/common/$part"
done
LUOSHU_TASK_SCOPE_PYTHON=python3; export LUOSHU_TASK_SCOPE_PYTHON
LUOSHU_RUNTIME_PATHS_PYTHON=python3; export LUOSHU_RUNTIME_PATHS_PYTHON
. "$MODDIR/common/runtime_paths.sh"
luoshu_runtime_paths_init "$MODDIR"
. "$MODDIR/common/background_task.sh"
PID="$LUOSHU_TASKS_DIR/background.pid"
cat >"$TMP/start.sh" <<'EOF'
#!/bin/sh
. "$MODDIR/common/background_task.sh"
LUOSHU_SCOPE_HANDOFF=1; export LUOSHU_SCOPE_HANDOFF
luoshu_start_detached "$LUOSHU_TASKS_DIR/background.pid" handoff-task "$LUOSHU_LOG_DIR/task.log" \
    sh -c 'sleep 30' handoff-task
EOF
# Completing a synchronous start hands ownership to its bounded worker.
sh "$MODDIR/common/task_scope.sh" request-run handoff-request 5 -- sh "$TMP/start.sh" >"$TMP/out" 2>"$TMP/err"
luoshu_task_pid_alive "$PID" handoff-task
grep -q '"handoffTasks": \["handoff-task"\]' "$LUOSHU_TASKS_DIR/request-handoff-request.pid.cleanup.json"
# Response-lost cancellation finds the exact handed-off worker in the ledger.
sh "$MODDIR/common/task_scope.sh" request-cancel handoff-request >"$TMP/cancel"
grep -q '"token":"handoff-request"' "$TMP/cancel"
grep -q '"cleaned":true' "$TMP/cancel"
! luoshu_task_pid_alive "$PID" handoff-task
test ! -e "$PID"
test ! -e "$PID.start"
# The same token cannot kill a later task occupying the old PID file.
luoshu_start_detached "$PID" newer-task "$LUOSHU_LOG_DIR/task.log" sh -c 'sleep 30' newer-task
sh "$MODDIR/common/task_scope.sh" request-cancel handoff-request >"$TMP/cancel-again"
luoshu_task_pid_alive "$PID" newer-task
luoshu_stop_task_pid "$PID" newer-task >"$TMP/stop"
test ! -e "$PID"
test ! -e "$PID.boot"
test ! -e "$PID.task"
test ! -e "$PID.owner.json"
test -z "$(find "$LUOSHU_TMP_DIR" -mindepth 1 -print -quit)"
printf 'task_scope_shell_test: PASS\n'
