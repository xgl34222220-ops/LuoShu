#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

FONT=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
if [ ! -s "$FONT" ]; then
    echo 'Font index deletion regression skipped: DejaVu Sans is unavailable.'
    exit 0
fi

MODULE="$TMP/module"
PUBLIC="$TMP/public"
mkdir -p "$MODULE/common" "$MODULE/config" "$PUBLIC/fonts"
cp "$ROOT/common/font_manager.sh" "$MODULE/common/font_manager.sh"
cp "$ROOT/common/font_manager_v4.sh" "$MODULE/common/font_manager_v4.sh"
cp "$ROOT/common/util_functions.sh" "$MODULE/common/util_functions.sh"
cp "$ROOT/common/util_functions_core.sh" "$MODULE/common/util_functions_core.sh"
cp "$ROOT/common/font_check.sh" "$MODULE/common/font_check.sh"
cp "$ROOT/common/font_library_cache.sh" "$MODULE/common/font_library_cache.sh"
for helper in task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py; do
    cp "$ROOT/common/$helper" "$MODULE/common/$helper"
done
printf 'id=LuoShu\nversion=test\nversionCode=1\n' > "$MODULE/module.prop"
HOST_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON" LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
unset LUOSHU_TASK_SCOPE_PID LUOSHU_TASK_SCOPE_PIDFILE LUOSHU_TASK_SCOPE_TASK LUOSHU_TASK_SCOPE_TMPDIR
unset LUOSHU_REAL_MODDIR LUOSHU_STATE_DIR LUOSHU_CONFIG_DIR LUOSHU_LOG_DIR LUOSHU_CACHE_DIR
unset LUOSHU_TASKS_DIR LUOSHU_TMP_DIR LUOSHU_BACKUP_DIR LUOSHU_REPORTS_DIR LUOSHU_RUNTIME_PATHS_MODULE
unset LUOSHU_SCOPE_ALLOW_HANDOFF LUOSHU_SCOPE_HANDOFF
cp "$FONT" "$PUBLIC/fonts/Alpha-Regular.ttf"
cp "$FONT" "$PUBLIC/fonts/Beta-Regular.ttf"

BEFORE=$(MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_manager.sh" action list refresh 2>>"$TMP/request-cleanup.stderr")
printf '%s\n' "$BEFORE" | grep -q '"count":2'
printf '%s\n' "$BEFORE" | grep -q '"id":"Alpha"'
printf '%s\n' "$BEFORE" | grep -q '"id":"Beta"'

DELETED=$(MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_manager.sh" action delete Alpha 2>>"$TMP/request-cleanup.stderr")
printf '%s\n' "$DELETED" | grep -q '"status":"ok"'
printf '%s\n' "$DELETED" | grep -q '"deleted":1'
test ! -e "$PUBLIC/fonts/Alpha-Regular.ttf"
test -s "$PUBLIC/fonts/Beta-Regular.ttf"

AFTER=$(MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_manager.sh" action list refresh 2>>"$TMP/request-cleanup.stderr")
printf '%s\n' "$AFTER" | grep -q '"count":1'
! printf '%s\n' "$AFTER" | grep -q '"id":"Alpha"'
printf '%s\n' "$AFTER" | grep -q '"id":"Beta"'

"$HOST_PYTHON" - "$MODULE/.luoshu-state/tasks" <<'PY'
import json
from pathlib import Path
import sys

tasks = Path(sys.argv[1])
proofs = list(tasks.glob('request-*.pid.cleanup.json'))
assert len(proofs) == 3, proofs
for path in proofs:
    proof = json.loads(path.read_text())
    assert proof['cleaned'] and not proof['leftoverPids'] and not proof['cleanupErrors'] and proof['result'] == 0, proof
for pattern in ('request-*.pid', 'request-*.pid.owner.json', 'request-*.pid.task',
                'request-*.pid.boot', 'request-*.pid.start'):
    assert not list(tasks.glob(pattern)), pattern
PY

# Inventory/delete implementation remains in the preserved current manager; the
# root manager is intentionally only a switch router.
! grep -Fq 'case "$_name|$_family"' "$ROOT/common/font_manager_v4.sh"
grep -Fq 'case "$_name" in' "$ROOT/common/font_manager_v4.sh"
grep -Fq 'case "$_family" in' "$ROOT/common/font_manager_v4.sh"
grep -q 'exec sh "$CURRENT_MANAGER" "$@"' "$ROOT/common/font_manager.sh"
echo 'Deleting one font through the router preserves every remaining font in the native index.'
