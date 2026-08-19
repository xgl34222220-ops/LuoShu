#!/bin/sh
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
