#!/bin/sh
# Provider success is determined by the exact targets from the current transaction being visible
# with the expected content in the Play Store's real parent zygote. The tests source and execute the
# production helpers and _gfp_apply_once itself; there is no copied verification implementation.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
. "$ROOT/common/google_font_provider_bridge.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
PROC="$TMP/proc"
TARGET="$TMP/provider/GoogleSans-Regular.ttf"
SOURCE="$TMP/source.ttf"
CLONE="$TMP/clone.ttf"
TXN="$TMP/transaction.conf"
mkdir -p "$PROC" "$(dirname "$TARGET")"
dd if=/dev/zero of="$TARGET" bs=2048 count=1 2>/dev/null
cp "$TARGET" "$SOURCE"
cp "$TARGET" "$CLONE"
printf 'current-clone\n' >> "$CLONE"

make_proc() {
    _mp_pid="$1"
    _mp_cmd="$2"
    _mp_parent="$3"
    mkdir -p "$PROC/$_mp_pid"
    printf '%s\000' "$_mp_cmd" > "$PROC/$_mp_pid/cmdline"
    printf 'Name:\t%s\nPPid:\t%s\n' "$_mp_cmd" "$_mp_parent" > "$PROC/$_mp_pid/status"
    : > "$PROC/$_mp_pid/mounts"
}

install_target() {
    _it_pid="$1"
    _it_content="$2"
    mkdir -p "$PROC/$_it_pid/root$(dirname "$TARGET")"
    cp "$_it_content" "$PROC/$_it_pid/root$TARGET"
    printf 'font-bind %s ext4 ro,relatime 0 0\n' "$TARGET" > "$PROC/$_it_pid/mounts"
}

write_transaction() {
    printf '%s|%s|%s|%s\n' \
        "$TARGET" "$CLONE" "$(_gfp_hash "$TARGET")" "$(_gfp_hash "$CLONE")" > "$TXN"
}

make_proc 900 zygote64 1
make_proc 901 com.android.vending 900
make_proc 902 zygote 1
write_transaction
export LUOSHU_PROC_ROOT="$PROC"

pidof() {
    for _po_name in "$@"; do
        case "$_po_name" in
            zygote64) printf '900\n' ;;
            zygote) [ -f "$PROC/.second-zygote" ] && printf '902\n' ;;
            com.android.vending) [ -f "$PROC/.vending-alive" ] && printf '901\n' ;;
        esac
    done
}

CASE='运行中的 Play 商店只校验实际父 zygote'
install_target 900 "$CLONE"
: > "$PROC/.vending-alive"
: > "$PROC/.second-zygote"
ok _gfp_verify_relevant_zygotes "$TXN"
eq "$_gfp_zygote_scope" vending-parent
eq "$_gfp_zygote_seen" 1
eq "$_gfp_zygote_verified" 1

CASE='同路径的旧字体不能冒充本次绑定'
install_target 900 "$TARGET"
no _gfp_verify_relevant_zygotes "$TXN"
eq "$_gfp_zygote_verified" 0
ok printf '%s\n' "$_gfp_zygote_verify_first_error" | grep -q 'target-hash-mismatch'

CASE='仅有相似 provider 路径不能冒充目标'
printf 'font-bind %s/other.ttf ext4 ro 0 0\n' "$(dirname "$TARGET")" > "$PROC/900/mounts"
no _gfp_verify_relevant_zygotes "$TXN"
ok printf '%s\n' "$_gfp_zygote_verify_first_error" | grep -q 'target-not-mounted'

CASE='Play 商店未运行时所有应用 zygote 都必须完整'
rm -f "$PROC/.vending-alive"
install_target 900 "$CLONE"
no _gfp_verify_relevant_zygotes "$TXN"
eq "$_gfp_zygote_scope" all-app-zygotes
eq "$_gfp_zygote_seen" 2
eq "$_gfp_zygote_verified" 1
install_target 902 "$CLONE"
ok _gfp_verify_relevant_zygotes "$TXN"
eq "$_gfp_zygote_verified" 2

# Exercise the real apply finalization with controlled clone generation and mount operations.
MODDIR="$TMP/module"
MODULE_DIR="$MODDIR"
CACHE="$MODDIR/config/google-font-provider"
STATE="$MODDIR/config/google-font-provider-mounts.conf"
LOG="$MODDIR/logs/google-font-provider.log"
mkdir -p "$CACHE" "$MODDIR/logs"
_gfp_active_font() { printf 'custom\n'; }
_gfp_targets() { printf '%s\n' "$TARGET"; }
_gfp_weight() { printf '400\n'; }
_gfp_source_for_weight() { printf '%s\n' "$SOURCE"; }
_gfp_build_clone() { printf '%s\n' "$CLONE"; }
_gfp_namespace_pids() { printf '900\n901\n'; }
_gfp_mount_in_pid() { _gfp_mount_mode=plain; _gfp_mount_detail=; return 0; }
am() {
    printf '%s\n' "$*" >> "$PROC/.am-calls"
    case "$*" in *force-stop*) rm -f "$PROC/.vending-alive" ;; esac
    return 0
}

CASE='真实 apply：完整父 zygote 才停止 Play 商店'
install_target 900 "$CLONE"
: > "$PROC/.vending-alive"
: > "$PROC/.am-calls"
LUOSHU_GOOGLE_FONT_DRY_RUN=0
export LUOSHU_GOOGLE_FONT_DRY_RUN
ok _gfp_apply_once
ok test -s "$STATE"
ok grep -q 'force-stop com.android.vending' "$PROC/.am-calls"
no test -e "$PROC/.vending-alive"
ok grep -q 'zygote校验=完整' "$LOG"
ok grep -q '已停止 Play 商店进程' "$LOG"

CASE='真实 apply：哈希不符时保留撤销清单但不停止应用'
install_target 900 "$TARGET"
: > "$PROC/.vending-alive"
: > "$PROC/.am-calls"
RC=0
_gfp_apply_once || RC=$?
eq "$RC" 1
ok test -s "$STATE"
no test -s "$PROC/.am-calls"
ok test -e "$PROC/.vending-alive"
ok grep -q 'zygote校验=不完整' "$LOG"

CASE='prepare 不得覆盖真实挂载的撤销清单'
printf 'existing-undo-list\n' > "$STATE"
: > "$PROC/.am-calls"
LUOSHU_GOOGLE_FONT_DRY_RUN=1
export LUOSHU_GOOGLE_FONT_DRY_RUN
ok _gfp_apply_once
eq "$(cat "$STATE")" existing-undo-list
no test -s "$PROC/.am-calls"

CASE='源码契约'
BRIDGE="$ROOT/common/google_font_provider_bridge.sh"
ok sh -n "$BRIDGE"
ok grep -q '_gfp_vending_parent_zygotes' "$BRIDGE"
ok grep -q '_gfp_verify_pid_state' "$BRIDGE"
ok grep -q 'target-hash-mismatch' "$BRIDGE"
no grep -q "grep -q 'files/fonts'" "$BRIDGE"
no grep -q 'LUOSHU_GOOGLE_FONT_VERIFY_WAIT' "$BRIDGE"
no grep -q '已重启 Play 商店' "$BRIDGE"

printf 'Provider zygote verification tests passed.\n'
