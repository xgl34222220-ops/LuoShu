#!/bin/sh
# #199: a device-font-cache pending marker must never mean "wait forever". It carries
# started/deadline/failures, expires into cacheState=failed:<reason>, and a failed marker is
# never rebuilt in the background. The App reads it through `check-deadline`.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='设备对齐缓存超时出口'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/device_font_cache.sh" "$MOD/common/device_font_cache.sh"
export MODDIR="$MOD" MODULE_DIR="$MOD"
PENDING="$MOD/config/device-font-cache-pending.conf"
FAILURES="$MOD/config/device-font-cache-failures.conf"
NOW=1000000

LUOSHU_CACHE_PENDING_TIMEOUT=600
_dfcache_module() { printf '%s\n' "$MOD"; }
_dfcache_log() { printf '%s\n' "$*" >> "$MOD/logs/cache.log"; }
. "$MOD/common/device_font_cache.sh"
_dfcache_now() { printf '%s\n' "$NOW"; }
_dfcache_template_key() { printf 'tpl\n'; }
_dfcache_source_key() { printf 'src\n'; }
_dfcache_id() { printf 'cache-id\n'; }
_dfcache_autostart_pending() { :; }

CASE='schedule 写入 started/deadline/failures'
device_font_cache_schedule Demo >/dev/null
ok grep -qx 'cacheState=pending' "$PENDING"
ok grep -qx "started=$NOW" "$PENDING"
ok grep -qx "deadline=$((NOW + 600))" "$PENDING"
ok grep -qx 'failures=0' "$PENDING"
eq "$(device_font_cache_state | sed -n 's/^cacheState=//p')" pending

CASE='未到期保持 pending'
NOW=$((1000000 + 599))
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" pending
ok grep -qx 'cacheState=pending' "$PENDING"

CASE='构建锁或前台事务进行中不判超时'
NOW=$((1000000 + 5000))
mkdir -p "$MOD/.device-font-cache.lock"
printf '%s\n' "$$" > "$MOD/.device-font-cache.lock/pid"
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" pending
rm -rf "$MOD/.device-font-cache.lock"
mkdir -p "$MOD/.font_switch.lock"
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" pending
rm -rf "$MOD/.font_switch.lock"

CASE='只读 state 报告超时但不改写待办（luoshu-health 只读契约）'
eq "$(device_font_cache_state | sed -n 's/^cacheState=//p')" failed:timeout
ok grep -qx 'cacheState=pending' "$PENDING"

CASE='到期后转为 failed:timeout'
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" failed:timeout
ok grep -qx 'state=failed' "$PENDING"
ok grep -qx 'cacheState=failed:timeout' "$PENDING"
ok grep -qx 'font=Demo' "$PENDING"
ok grep -q '^failedAt=' "$PENDING"

CASE='failed 待办不得被后台构建重新拉起'
set +e
_dfcache_build_pending_inner
RC=$?
set -e
eq "$RC" 2
ok grep -qx 'cacheState=failed:timeout' "$PENDING"

CASE='failed 状态幂等'
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" failed:timeout

CASE='有构建失败记录时到期原因为 build-failed'
NOW=2000000
device_font_cache_schedule Demo >/dev/null
_dfcache_failure_record build
ok grep -qx 'failures=1' "$PENDING"
ok grep -qx 'cacheState=pending' "$PENDING"
NOW=$((2000000 + 601))
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" failed:build-failed

CASE='失败计数达到上限立即转为 failed'
NOW=3000000
device_font_cache_schedule Demo >/dev/null
_dfcache_pending_set_field failures 3
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" failed:build-retry-exhausted

CASE='旧版 v4 待办（只有 time=）按 time 推导截止时间'
printf 'state=pending\nfont=Old\ntime=%s\n' 4000000 > "$PENDING"
rm -f "$FAILURES"
NOW=$((4000000 + 10))
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" pending
ok grep -qx 'started=4000000' "$PENDING"
ok grep -qx 'deadline=4000600' "$PENDING"
NOW=$((4000000 + 600))
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" failed:timeout

CASE='没有任何时间戳的旧待办从现在开始计时'
printf 'state=pending\nfont=Old\n' > "$PENDING"
NOW=5000000
eq "$(device_font_cache_check_deadline | sed -n 's/^cacheState=//p')" pending
ok grep -qx 'deadline=5000600' "$PENDING"

CASE='重新扫描只清除 failed 待办'
eq "$(device_font_cache_clear_failed | sed -n 's/^cacheState=//p')" pending
ok test -s "$PENDING"
NOW=$((5000000 + 700))
device_font_cache_check_deadline >/dev/null
printf 'count=3\n' > "$FAILURES"
eq "$(device_font_cache_clear_failed | sed -n 's/^cacheState=//p')" none
no test -e "$PENDING"
no test -e "$FAILURES"

CASE='显式应用会用新意图替换 failed 待办'
printf 'state=failed\ncacheState=failed:timeout\nfont=Demo\n' > "$PENDING"
NOW=6000000
device_font_cache_schedule Demo >/dev/null
ok grep -qx 'cacheState=pending' "$PENDING"
ok grep -qx 'deadline=6000600' "$PENDING"

CASE='CLI 子命令'
rm -f "$PENDING"
eq "$(MODDIR="$MOD" sh "$MOD/common/device_font_cache.sh" state)" 'cacheState=none'
eq "$(MODDIR="$MOD" sh "$MOD/common/device_font_cache.sh" check-deadline)" 'cacheState=none'
eq "$(MODDIR="$MOD" sh "$MOD/common/device_font_cache.sh" clear-failed)" 'cacheState=none'

CASE='语法'
ok sh -n "$ROOT/common/device_font_cache.sh"
printf 'Device aligned-cache timeout tests passed.\n'
