#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$TMP/public/fonts" "$TMP/export"
for helper in app_bridge.sh task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py util_functions.sh util_functions_core.sh; do
    cp "$ROOT/common/$helper" "$MODULE/common/$helper"
done
printf 'id=LuoShu\nversion=test\nversionCode=1\n' > "$MODULE/module.prop"
HOST_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON" LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
# Start real ownership in an isolated installed-module fixture, never the checkout.
unset LUOSHU_TASK_SCOPE_PID LUOSHU_TASK_SCOPE_PIDFILE LUOSHU_TASK_SCOPE_TASK LUOSHU_TASK_SCOPE_TMPDIR
unset LUOSHU_REAL_MODDIR LUOSHU_STATE_DIR LUOSHU_CONFIG_DIR LUOSHU_LOG_DIR LUOSHU_CACHE_DIR
unset LUOSHU_TASKS_DIR LUOSHU_TMP_DIR LUOSHU_BACKUP_DIR LUOSHU_REPORTS_DIR LUOSHU_RUNTIME_PATHS_MODULE
unset LUOSHU_SCOPE_ALLOW_HANDOFF LUOSHU_SCOPE_HANDOFF

preview_source() {
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_PUBLIC_DIR="$TMP/public" \
        sh "$MODULE/common/app_bridge.sh" preview_source "$@" 2>>"$TMP/request-cleanup.stderr"
}

printf regular > "$TMP/public/fonts/Demo-Regular.ttf"
printf bold > "$TMP/public/fonts/Demo-Bold.ttf"
printf extra > "$TMP/public/fonts/Demo-ExtraBold.ttf"

OUTPUT=$(preview_source Demo 400)
printf '%s\n' "$OUTPUT" | grep -q '"status":"ok"'
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-Regular.ttf"'

OUTPUT=$(preview_source Demo 700)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-Bold.ttf"'

OUTPUT=$(preview_source Demo 800)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-ExtraBold.ttf"'


printf only-bold > "$TMP/public/fonts/Only-Bold.ttf"
OUTPUT=$(preview_source Only 400)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Only-Bold.ttf"'

"$HOST_PYTHON" - "$MODULE/.luoshu-state/tasks" <<'PY'
import json
from pathlib import Path
import sys

tasks = Path(sys.argv[1])
proofs = list(tasks.glob('request-*.pid.cleanup.json'))
assert len(proofs) == 4, proofs
for path in proofs:
    proof = json.loads(path.read_text())
    assert proof['cleaned'] and not proof['leftoverPids'] and not proof['cleanupErrors'] and proof['result'] == 0, proof
for pattern in ('request-*.pid', 'request-*.pid.owner.json', 'request-*.pid.task',
                'request-*.pid.boot', 'request-*.pid.start'):
    assert not list(tasks.glob(pattern)), pattern
PY

echo 'Native weighted preview source regression test passed.'
