from pathlib import Path
import re

ROOT = Path('.')

def load(path):
    return (ROOT / path).read_text()

def save(path, text):
    (ROOT / path).write_text(text)

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 exact match, got {count}')
    return text.replace(old, new, 1)

def regex_once(text, pattern, repl, label):
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 regex match, got {count}')
    return out

# 1) Cache: sanitize failure limit and centralize robust stale-lock handling.
path = 'common/device_font_cache.sh'
s = load(path)
s = replace_once(
    s,
    'LUOSHU_CACHE_FAILURE_LIMIT="${LUOSHU_CACHE_FAILURE_LIMIT:-3}"\n',
    'LUOSHU_CACHE_FAILURE_LIMIT="${LUOSHU_CACHE_FAILURE_LIMIT:-3}"\n'
    'case "$LUOSHU_CACHE_FAILURE_LIMIT" in \'\'|*[!0-9]*) LUOSHU_CACHE_FAILURE_LIMIT=3 ;; esac\n'
    '[ "$LUOSHU_CACHE_FAILURE_LIMIT" -ge 1 ] 2>/dev/null || LUOSHU_CACHE_FAILURE_LIMIT=1\n',
    'sanitize cache failure limit',
)

helpers = r'''
# Cache locks survive in the persistent module directory, so a reboot/OOM can leave one behind.
# Reuse the font-switch identity lock helpers (PID + starttime + boot_id) when available; this
# avoids treating a recycled PID after reboot as the old cache worker.
_dfcache_load_lock_helpers() {
    type luoshu_font_lock_acquire >/dev/null 2>&1 &&
        type luoshu_font_lock_reap_stale >/dev/null 2>&1 &&
        type luoshu_font_lock_release >/dev/null 2>&1 && return 0
    _dfcl_module="$(_dfcache_module)"
    _dfcl_util="$_dfcl_module/common/util_functions.sh"
    [ -f "$_dfcl_util" ] && . "$_dfcl_util"
    type luoshu_font_lock_acquire >/dev/null 2>&1 &&
        type luoshu_font_lock_reap_stale >/dev/null 2>&1 &&
        type luoshu_font_lock_release >/dev/null 2>&1
}

_dfcache_lock_reap_stale() {
    _dfclr_lock="$1"
    [ -e "$_dfclr_lock" ] || return 0
    if _dfcache_load_lock_helpers; then
        luoshu_font_lock_active "$_dfclr_lock" >/dev/null 2>&1 && return 1
        luoshu_font_lock_reap_stale "$_dfclr_lock" >/dev/null 2>&1 || true
        [ ! -e "$_dfclr_lock" ]
        return $?
    fi
    # Minimal fallback for stripped/test environments where util_functions.sh is unavailable.
    _dfclr_owner=$(sed -n '1p' "$_dfclr_lock/pid" 2>/dev/null)
    case "$_dfclr_owner" in
        ''|*[!0-9]*)
            sleep 1 2>/dev/null || true
            _dfclr_owner=$(sed -n '1p' "$_dfclr_lock/pid" 2>/dev/null)
            ;;
    esac
    case "$_dfclr_owner" in
        ''|*[!0-9]*) ;;
        *) kill -0 "$_dfclr_owner" 2>/dev/null && return 1 ;;
    esac
    rm -f "$_dfclr_lock/pid" 2>/dev/null || true
    rmdir "$_dfclr_lock" 2>/dev/null || true
    [ ! -e "$_dfclr_lock" ]
}

_dfcache_lock_acquire() {
    _dfcla_lock="$1"
    if _dfcache_load_lock_helpers; then
        luoshu_font_lock_acquire "$_dfcla_lock" "$$"
        return $?
    fi
    _dfcache_lock_reap_stale "$_dfcla_lock" >/dev/null 2>&1 || {
        [ ! -e "$_dfcla_lock" ] || return 2
    }
    mkdir "$_dfcla_lock" 2>/dev/null || return 2
    printf '%s\n' "$$" > "$_dfcla_lock/pid" 2>/dev/null || {
        rmdir "$_dfcla_lock" 2>/dev/null || true
        return 1
    }
    return 0
}

_dfcache_lock_release() {
    _dfclx_lock="$1"
    if _dfcache_load_lock_helpers; then
        luoshu_font_lock_release "$_dfclx_lock" "$$" >/dev/null 2>&1 && return 0
    fi
    _dfclx_owner=$(sed -n '1p' "$_dfclx_lock/pid" 2>/dev/null)
    [ -z "$_dfclx_owner" ] || [ "$_dfclx_owner" = "$$" ] || return 1
    rm -f "$_dfclx_lock/pid" 2>/dev/null || true
    rmdir "$_dfclx_lock" 2>/dev/null || true
    [ ! -e "$_dfclx_lock" ]
}
'''
s = replace_once(s, '\n_dfcache_autostart_pending() {\n', helpers + '\n_dfcache_autostart_pending() {\n', 'insert cache lock helpers')

s = regex_once(
    s,
    r'''    # A build killed by the OOM reaper or by a reboot leaves the lock directory behind, and nothing\n    # reaped it, so the cache stayed "already running" forever\. Reuse the switch lock's PID ownership\.\n    if type luoshu_font_lock_reap_stale >/dev/null 2>&1; then\n        luoshu_font_lock_reap_stale "\$_dfc_lock" >/dev/null 2>&1 \|\| true\n    elif \[ -d "\$_dfc_lock" \]; then\n        _dfc_owner=\$\(cat "\$_dfc_lock/pid" 2>/dev/null\)\n        case "\$_dfc_owner" in\n            ''\|\*\[!0-9\]\*\) rm -rf "\$_dfc_lock" 2>/dev/null \|\| true ;;\n            \*\) kill -0 "\$_dfc_owner" 2>/dev/null \|\| rm -rf "\$_dfc_lock" 2>/dev/null \|\| true ;;\n        esac\n    fi\n    if ! mkdir "\$_dfc_lock" 2>/dev/null; then\n        _dfcache_log '后台对齐缓存任务已经在运行'\n        return 2\n    fi\n    printf '%s\\n' "\$\$" > "\$_dfc_lock/pid" 2>/dev/null \|\| true\n    trap 'rm -f "'"\$_dfc_lock"'/pid" 2>/dev/null; rmdir "'"\$_dfc_lock"'" 2>/dev/null \|\| true' EXIT HUP INT TERM\n''',
    '''    _dfcache_lock_acquire "$_dfc_lock"\n    _dfc_lock_rc=$?\n    case "$_dfc_lock_rc" in\n        0) ;;\n        2) _dfcache_log '后台对齐缓存任务已经在运行'; return 2 ;;\n        *) _dfcache_log '后台对齐缓存锁创建失败'; return 1 ;;\n    esac\n    trap '_dfcache_lock_release "$_dfc_lock" >/dev/null 2>&1 || true' EXIT HUP INT TERM\n''',
    'replace cache lock acquisition',
)

s = replace_once(
    s,
    '        rm -f "$_dfc_lock/pid" 2>/dev/null || true\n        rmdir "$_dfc_lock" 2>/dev/null || true\n        trap - EXIT HUP INT TERM\n',
    '        _dfcache_lock_release "$_dfc_lock" >/dev/null 2>&1 || true\n        trap - EXIT HUP INT TERM\n',
    'replace cache lock success release',
)
save(path, s)

# 2) Boot launcher: reap a stale cache lock before deciding a worker is already active.
path = 'common/device_font_dynamic_guard.sh'
s = load(path)
s = replace_once(
    s,
    '''    if [ -d "$_dfpr_module_dir/.device-font-cache.lock" ]; then\n        _dfpr_log INFO '设备对齐缓存后台任务已经在运行'\n        return 0\n    fi\n''',
    '''    _dfpr_cache_lock="$_dfpr_module_dir/.device-font-cache.lock"\n    if [ -e "$_dfpr_cache_lock" ]; then\n        if type _dfcache_lock_reap_stale >/dev/null 2>&1; then\n            _dfcache_lock_reap_stale "$_dfpr_cache_lock" >/dev/null 2>&1 || true\n        elif type luoshu_font_lock_reap_stale >/dev/null 2>&1; then\n            luoshu_font_lock_reap_stale "$_dfpr_cache_lock" >/dev/null 2>&1 || true\n        fi\n        if [ -e "$_dfpr_cache_lock" ]; then\n            _dfpr_log INFO '设备对齐缓存后台任务已经在运行'\n            return 0\n        fi\n        _dfpr_log INFO '已回收陈旧设备对齐缓存锁'\n    fi\n''',
    'reap stale lock in boot launcher',
)
save(path, s)

# 3) Provider PID scan: preserve the old union semantics while reducing process creation to a
# fixed-cost scan. Also resolve the PID list once per apply/restore instead of once per target.
path = 'common/google_font_provider_bridge.sh'
s = load(path)
provider_fn = r'''_gfp_namespace_pids() {
    _gfp_proc_root="${LUOSHU_PROC_ROOT:-/proc}"
    {
        # Named fast paths cover the common processes.
        for _gfp_pid in $(pidof zygote64 zygote zygote_secondary zygote64_32 zygote_ocomp 2>/dev/null); do
            printf '%s\n' "$_gfp_pid"
        done
        for _gfp_pid in $(pidof com.android.vending 2>/dev/null); do
            printf '%s\n' "$_gfp_pid"
        done
        for _gfp_pid in $(pidof com.google.android.gms com.google.android.gms.persistent com.google.android.gms.unstable 2>/dev/null); do
            printf '%s\n' "$_gfp_pid"
        done

        # Preserve the previous wildcard semantics for GMS subprocesses such as
        # com.google.android.gms:phenotype. This is one grep process for the whole proc tree, not
        # two child processes per PID. The result is merged with pidof rather than replacing it.
        grep -al -e zygote -e com.android.vending -e com.google.android.gms \
            "$_gfp_proc_root"/[0-9]*/cmdline 2>/dev/null |
            while IFS= read -r _gfp_path; do
                [ -n "$_gfp_path" ] || continue
                _gfp_rest=${_gfp_path#"$_gfp_proc_root"/}
                _gfp_pid=${_gfp_rest%%/*}
                case "$_gfp_pid" in ''|*[!0-9]*) continue ;; esac
                printf '%s\n' "$_gfp_pid"
            done
    } | awk '/^[0-9]+$/ && !seen[$0]++'
}'''
s = regex_once(
    s,
    r'_gfp_namespace_pids\(\) \{.*?\n\}\n\n# bind 的源必须由目标进程自己的 mount namespace 解析。',
    provider_fn + '\n\n# bind 的源必须由目标进程自己的 mount namespace 解析。',
    'replace provider namespace pid function',
)

s = replace_once(
    s,
    '    _gfp_missing_first=\n    while IFS= read -r _gfp_target; do\n',
    '    _gfp_missing_first=\n    _gfp_namespace_pid_list=\n    if [ "${LUOSHU_GOOGLE_FONT_DRY_RUN:-0}" != 1 ]; then\n        _gfp_namespace_pid_list=$(_gfp_namespace_pids)\n    fi\n    while IFS= read -r _gfp_target; do\n',
    'cache provider pid list per apply',
)
s = replace_once(
    s,
    '            for _gfp_pid in $(_gfp_namespace_pids); do\n',
    '            for _gfp_pid in $_gfp_namespace_pid_list; do\n',
    'use cached provider pid list in apply',
)
s = replace_once(
    s,
    '''_gfp_restore() {\n    [ -s "$STATE" ] || return 0\n    while IFS='|' read -r _gfp_target _gfp_source _gfp_th _gfp_sh; do\n        [ -n "$_gfp_target" ] || continue\n        for _gfp_pid in $(_gfp_namespace_pids); do\n''',
    '''_gfp_restore() {\n    [ -s "$STATE" ] || return 0\n    _gfp_restore_pids=$(_gfp_namespace_pids)\n    while IFS='|' read -r _gfp_target _gfp_source _gfp_th _gfp_sh; do\n        [ -n "$_gfp_target" ] || continue\n        for _gfp_pid in $_gfp_restore_pids; do\n''',
    'cache provider pid list in restore',
)

# Make the bridge safe to source for targeted function tests; production already executes it via sh.
s = replace_once(
    s,
    '''case "${1:-boot}" in\n    boot) _gfp_boot ;;\n    apply|now) _gfp_apply_once ;;\n    prepare) LUOSHU_GOOGLE_FONT_DRY_RUN=1 _gfp_apply_once ;;\n    restore) _gfp_restore ;;\n    invalidate)\n        _gfp_restore >/dev/null 2>&1 || true\n        rm -rf "$CACHE" "$STATE" 2>/dev/null || true\n        ;;\n    *) echo "Usage: $0 {boot|apply|prepare|restore|invalidate}" >&2; exit 2 ;;\nesac\n''',
    '''if [ "${0##*/}" = google_font_provider_bridge.sh ]; then\n    case "${1:-boot}" in\n        boot) _gfp_boot ;;\n        apply|now) _gfp_apply_once ;;\n        prepare) LUOSHU_GOOGLE_FONT_DRY_RUN=1 _gfp_apply_once ;;\n        restore) _gfp_restore ;;\n        invalidate)\n            _gfp_restore >/dev/null 2>&1 || true\n            rm -rf "$CACHE" "$STATE" 2>/dev/null || true\n            ;;\n        *) echo "Usage: $0 {boot|apply|prepare|restore|invalidate}" >&2; exit 2 ;;\n    esac\nfi\n''',
    'make provider bridge source-safe',
)
save(path, s)

# 4) Strengthen the provider regression: exercise the real function against a fake proc root and
# prove that a partial pidof hit does not suppress wildcard-discovered GMS/Vending processes.
provider_test = r'''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='provider 命名空间 PID 解析'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
FAKE="$TMP/proc"
mkdir -p "$FAKE"

# The bridge is source-safe so the real PID resolver can be tested without executing apply/boot.
. "$ROOT/common/google_font_provider_bridge.sh"
ok type _gfp_namespace_pids >/dev/null

make_proc() {
    _pid="$1"
    _cmd="$2"
    mkdir -p "$FAKE/$_pid"
    printf '%s\000' "$_cmd" > "$FAKE/$_pid/cmdline"
}
make_proc 1700 'com.google.android.gms:phenotype'
make_proc 1800 'com.android.vending:background'
make_proc 1900 'unrelated.app'
make_proc 2000 'zygote64'

# Deliberately return only a partial named set. The old optimization returned early as soon as
# zygote was found, which silently dropped GMS/Vending subprocesses that only the wildcard scan sees.
pidof() {
    case "$*" in
        *zygote*) printf '1500\n' ;;
        *com.google.android.gms*) printf '1600\n' ;;
        *) return 1 ;;
    esac
}
LUOSHU_PROC_ROOT="$FAKE"
export LUOSHU_PROC_ROOT
_gfp_namespace_pids > "$TMP/out"

CASE='pidof 命中不能吞掉通配发现的额外进程'
ok command grep -qx 1500 "$TMP/out"
ok command grep -qx 1600 "$TMP/out"
ok command grep -qx 1700 "$TMP/out"
ok command grep -qx 1800 "$TMP/out"
ok command grep -qx 2000 "$TMP/out"
no command grep -qx 1900 "$TMP/out"
eq "$(wc -l < "$TMP/out" | tr -d '[:space:]')" 5

CASE='源码不得恢复逐进程 fork'
no command grep -q 'basename "\$_gfp_proc"' "$ROOT/common/google_font_provider_bridge.sh"
no command grep -q '_gfp_cmd=$(tr' "$ROOT/common/google_font_provider_bridge.sh"
ok command grep -q 'LUOSHU_PROC_ROOT:-/proc' "$ROOT/common/google_font_provider_bridge.sh"
ok command grep -q '_gfp_namespace_pid_list=$(_gfp_namespace_pids)' "$ROOT/common/google_font_provider_bridge.sh"

CASE='语法'
ok sh -n "$ROOT/common/google_font_provider_bridge.sh"
printf 'Provider namespace PID scan tests passed.\n'
'''
save('scripts/provider_pid_scan_test.sh', provider_test)

# 5) Extend cache regression to cover the actual boot gate: stale lock must be reaped before launch;
# a live lock must still prevent a duplicate worker.
path = 'scripts/device_font_cache_budget_test.sh'
s = load(path)
extra = r'''
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
'''
s = replace_once(s, "\nCASE='语法'\n", extra + "\nCASE='语法'\n", 'extend cache stale-lock test')
save(path, s)

print('fixup applied')
