#!/bin/sh
# The aligned cache is an enhancement: fonts are already live through the physical slot mapping
# before it runs. Without a failure budget its pending marker survived every failure and
# service.sh relaunched the full fontTools build on every boot, forever, which is what users see
# as a font module permanently eating CPU.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='后台对齐缓存失败预算'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/device_font_cache.sh" "$MOD/common/device_font_cache.sh"
export MODDIR="$MOD" MODULE_DIR="$MOD"
PENDING="$MOD/config/device-font-cache-pending.conf"
FAILURES="$MOD/config/device-font-cache-failures.conf"

BUILD_RC=1
_dfcache_module() { printf '%s\n' "$MOD"; }
_dfcache_log() { printf '%s\n' "$*" >> "$MOD/logs/cache.log"; }
. "$MOD/common/device_font_cache.sh"
# Stand in for the expensive builder; the wrapper under test is what turns its result into policy.
_dfcache_build_pending_inner() { return "$BUILD_RC"; }

write_pending() { printf 'state=pending\nfont=Demo\n' > "$PENDING"; }

CASE='失败必须计数且保留待办直到用完预算'
write_pending
BUILD_RC=1
device_font_cache_build_pending || true
ok test -s "$PENDING"
ok grep -qx 'count=1' "$FAILURES"
device_font_cache_build_pending || true
ok test -s "$PENDING"
ok grep -qx 'count=2' "$FAILURES"

CASE='用完预算后必须停止重试'
device_font_cache_build_pending || true
ok grep -qx 'count=3' "$FAILURES"
# The pending marker is what service.sh keys on at every boot. Once the budget is spent it has to
# be gone, otherwise the build is relaunched forever.
no test -e "$PENDING"

CASE='rc=2 表示本轮跳过，不能消耗预算'
rm -f "$FAILURES"
write_pending
BUILD_RC=2
device_font_cache_build_pending || true
no test -e "$FAILURES"
ok test -s "$PENDING"

CASE='成功必须清零计数'
printf 'count=2\n' > "$FAILURES"
BUILD_RC=0
device_font_cache_build_pending
no test -e "$FAILURES"

CASE='用户重新应用字体时预算重置'
printf 'count=9\n' > "$FAILURES"
_dfcache_template_key() { printf 'tpl\n'; }
_dfcache_source_key() { printf 'src\n'; }
_dfcache_id() { printf 'cache-id\n'; }
_dfcache_autostart_pending() { :; }
device_font_cache_schedule Demo >/dev/null
no test -e "$FAILURES"
ok test -s "$PENDING"

CASE='开机入口必须回收陈旧 cache lock 后继续启动'
. "$ROOT/common/device_font_dynamic_guard.sh"
_dfpr_module() { printf '%s\n' "$MOD"; }
_dfpr_log() { :; }
STARTED="$TMP/started"
_dfcache_run_service_lowpri() { printf 'started\n' > "$STARTED"; }
write_pending
mkdir -p "$MOD/.device-font-cache.lock"
printf '999999\n' > "$MOD/.device-font-cache.lock/pid"
_dfpr_launch_pending_cache
_i=0
while [ ! -s "$STARTED" ] && [ "$_i" -lt 20 ]; do
    sleep 0.05
    _i=$((_i + 1))
done
ok test -s "$STARTED"
no test -e "$MOD/.device-font-cache.lock"

CASE='活动 cache lock 必须阻止重复后台任务'
rm -f "$STARTED"
mkdir -p "$MOD/.device-font-cache.lock"
printf '%s\n' "$$" > "$MOD/.device-font-cache.lock/pid"
_dfpr_launch_pending_cache
sleep 0.1
no test -s "$STARTED"
rm -f "$MOD/.device-font-cache.lock/pid"
rmdir "$MOD/.device-font-cache.lock"

CASE='语法'
ok sh -n "$ROOT/common/device_font_cache.sh"
ok sh -n "$ROOT/common/device_font_dynamic_guard.sh"
printf 'Device aligned-cache failure budget tests passed.\n'
