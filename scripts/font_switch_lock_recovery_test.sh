#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
MODDIR="$TMP/module"
cleanup() {
  [ ! -f "$MODDIR/common/task_scope.sh" ] || sh "$MODDIR/common/task_scope.sh" cancel-all "$MODDIR" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/logs"
cp "$ROOT/common/util_functions.sh" "$ROOT/common/util_functions_core.sh" "$MODDIR/common/"
for helper in task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py background_task.sh; do
  cp "$ROOT/common/$helper" "$MODDIR/common/$helper"
done
cp "$ROOT/module.prop" "$MODDIR/module.prop"
HOST_PYTHON="$(command -v python3)"
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON" LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
unset LUOSHU_TASK_SCOPE_PID LUOSHU_TASK_SCOPE_PIDFILE LUOSHU_TASK_SCOPE_TASK LUOSHU_TASK_SCOPE_TMPDIR
unset LUOSHU_REAL_MODDIR LUOSHU_STATE_DIR LUOSHU_CONFIG_DIR LUOSHU_LOG_DIR LUOSHU_CACHE_DIR
unset LUOSHU_TASKS_DIR LUOSHU_TMP_DIR LUOSHU_BACKUP_DIR LUOSHU_REPORTS_DIR LUOSHU_RUNTIME_PATHS_MODULE
unset LUOSHU_SCOPE_ALLOW_HANDOFF LUOSHU_SCOPE_HANDOFF LUOSHU_TASK_SCOPE_RUNNER
export MODDIR
MODULE_DIR="$MODDIR"; export MODULE_DIR
. "$MODDIR/common/util_functions.sh"
# Production libraries set +e; every fixture assertion must remain fail-fast.
set -eu
LOCK="$MODDIR/.font_switch.lock"
fail(){ echo "font_switch_lock_recovery_test: FAIL - $1" >&2; exit 1; }
stale(){ rm -rf "$LOCK" 2>/dev/null || true; mkdir "$LOCK"; printf '999999\nstarttime=1\nboot_id=stale\n' > "$LOCK/pid"; }

stale
rm -f "$LOCK" 2>/dev/null || true
[ -e "$LOCK" ] || fail 'rm -f premise changed'
luoshu_font_lock_force_clear "$LOCK" || fail 'directory force_clear failed'
[ ! -e "$LOCK" ] || fail 'directory lock remains'
printf '999999\n' > "$LOCK"
luoshu_font_lock_force_clear "$LOCK" || fail 'legacy force_clear failed'
stale
: > "$LOCK.owner.a"
luoshu_font_lock_force_clear "$LOCK" || fail 'owner cleanup failed'
[ ! -e "$LOCK.owner.a" ] || fail 'owner temp remains'

stale
luoshu_font_lock_busy "$LOCK" && fail 'stale lock marked busy' || true
[ -e "$LOCK" ] || fail 'busy must not reap'
luoshu_font_lock_force_clear "$LOCK" >/dev/null 2>&1 || true
luoshu_font_lock_acquire "$LOCK" "$$" || fail 'live acquire failed'
luoshu_font_lock_busy "$LOCK" || fail 'live lock not busy'
luoshu_font_lock_release "$LOCK" "$$" || fail 'live release failed'

# A live unrelated PID with another start time is a reused identity, not a
# reason to keep a dead font lock. Reaping its record must leave that PID alive.
mkdir "$LOCK"
printf '%s\nstarttime=1\nboot_id=%s\n' "$$" "$(cat /proc/sys/kernel/random/boot_id)" > "$LOCK/pid"
luoshu_font_lock_busy "$LOCK" && fail 'reused PID lock marked busy' || true
luoshu_font_lock_reap_stale "$LOCK" || fail 'reused PID lock was not reaped'
kill -0 "$$" || fail 'reused PID lock signalled unrelated process'

mkdir "$LOCK"
( sleep 0.2; printf '%s\n' "$$" > "$LOCK/pid" ) &
w=$!
LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS=1; export LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS
luoshu_font_lock_busy "$LOCK" || fail 'initializing lock falsely idle'
wait "$w"
luoshu_font_lock_force_clear "$LOCK" >/dev/null 2>&1 || true

mkdir "$LOCK"
LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS=0.1; export LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS
luoshu_font_lock_busy "$LOCK" && fail 'abandoned empty lock stayed busy' || true
[ -d "$LOCK" ] || fail 'busy reaped lock'
luoshu_font_lock_reap_stale "$LOCK" >/dev/null 2>&1 || true
[ ! -e "$LOCK" ] || fail 'reap failed'

cat > "$MODDIR/common/mix_weight_mode.sh" <<'EOS'
infer_mix_weight_mode() { printf 'auto\n'; }
EOS

for s in weighted_mix_task.sh multiweight_mix_task.sh; do
  cp "$ROOT/common/$s" "$MODDIR/common/"
  stale
  out="$TMP/$s.out"
  if command -v timeout >/dev/null 2>&1; then
    MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$TMP/public" timeout 60 sh "$MODDIR/common/$s" start A.ttf B.ttf C.ttf >"$out" 2>&1 || true
  else
    MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$TMP/public" sh "$MODDIR/common/$s" start A.ttf B.ttf C.ttf >"$out" 2>&1 || true
  fi
  grep -q '字体正在切换中' "$out" && fail "$s stale lock still blocks start" || true
  [ ! -e "$LOCK" ] || fail "$s did not reap stale lock"
  sh "$MODDIR/common/task_scope.sh" cancel-all "$MODDIR" >/dev/null || fail "$s task cleanup failed"
  "$HOST_PYTHON" - "$MODDIR/.luoshu-state/tasks" <<'PY'
import json
from pathlib import Path
import sys
tasks = Path(sys.argv[1])
proofs = list(tasks.glob('request-*.pid.cleanup.json'))
assert proofs, 'standalone CLI did not execute its real request scope'
for path in tasks.glob('*.pid.cleanup.json'):
    proof = json.loads(path.read_text())
    assert proof['cleaned'] and not proof['leftoverPids'] and not proof['cleanupErrors'], proof
for suffix in ('*.pid', '*.pid.owner.json', '*.pid.task', '*.pid.boot', '*.pid.start'):
    assert not list(tasks.glob(suffix)), suffix
PY
done

grep -q 'luoshu_font_lock_force_clear' "$ROOT/.luoshu-runtime/compat/v227/post-fs-data.sh" || fail 'post-fs force_clear missing'
for f in common/multiweight_mix_task.sh common/weighted_mix_task.sh .luoshu-runtime/core/service.sh common/device_font_cache.sh common/device_font_boot_verify.sh; do
  grep -q 'luoshu_font_lock_busy' "$ROOT/$f" || fail "$f busy missing"
done
# Root service is now a router: it must select the preserved v4 service when legacy mode is absent,
# while legacy mode intentionally skips v4 load verification/rebuild work entirely.
grep -q '.luoshu-runtime/core/service.sh' "$ROOT/service.sh" || fail 'service router missing v4 backend'
grep -q 'font_runtime_legacy_v14_4.conf' "$ROOT/service.sh" || fail 'service router missing legacy mode guard'
! grep -q 'device_font_load_verify.sh' "$ROOT/service.sh" || fail 'legacy router unexpectedly owns v4 load verification'
grep -q 'luoshu_font_lock_force_clear' "$ROOT/common/module_update_state.sh" || fail 'update force_clear missing'
echo 'font_switch_lock_recovery_test: PASS'
