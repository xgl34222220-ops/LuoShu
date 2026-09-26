#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/module/common" "$TMP/module/config" "$TMP/module/logs"
cp "$ROOT/common/background_task.sh" "$TMP/module/common/background_task.sh"
cat >"$TMP/module/common/dummy_worker.sh" <<'EOS'
#!/bin/sh
trap '' HUP
[ "$1" = worker ]
printf 'started\n' >"$DUMMY_STATE"
sleep 2
printf 'finished\n' >"$DUMMY_STATE"
EOS
chmod 0755 "$TMP/module/common/dummy_worker.sh"
(
  MODDIR="$TMP/module"
  DUMMY_STATE="$TMP/state"; export DUMMY_STATE
  . "$TMP/module/common/background_task.sh"
  luoshu_start_detached "$TMP/module/config/dummy.pid" dummy-task "$TMP/module/logs/dummy.log" sh "$TMP/module/common/dummy_worker.sh" worker dummy-task
)
for _n in 1 2 3 4 5; do [ "$(cat "$TMP/state" 2>/dev/null)" = finished ] && break; sleep 1; done
[ "$(cat "$TMP/state" 2>/dev/null)" = finished ]
grep -q 'nohup setsid\|toybox nohup toybox setsid' "$ROOT/common/background_task.sh"
grep -q 'luoshu_start_detached.*worker' "$ROOT/common/weighted_mix_task.sh"
grep -q 'luoshu_start_detached.*worker' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'luoshu_start_detached.*worker' "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
grep -q 'luoshu_start_detached.*worker' "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
grep -q 'exec sh "$MIX_ROUTER"' "$ROOT/common/font_mix.sh"
# The App entry must delegate without loading validators or enumerating fonts.
sh "$ROOT/scripts/mix_entry_router_test.sh"
# 嵌套完整复合引擎即使丢失启动输出，也必须从持久化任务文件接管。
sh "$ROOT/scripts/nested_mix_task_handoff_test.sh"
echo 'Detached root font workers survive their submitting shell, nested handoff, and weighted jobs queue immediately.'
