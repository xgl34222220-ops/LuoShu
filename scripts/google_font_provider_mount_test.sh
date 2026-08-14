#!/bin/sh
# 洛书 - provider 桥命名空间挂载回归测试
set -eu

ROOT="${ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)}"
BRIDGE="${BRIDGE:-$ROOT/common/google_font_provider_bridge.sh}"
fail() { echo "google_font_provider_mount_test: FAIL - $1" >&2; exit 1; }

# 1. /proc/1/root 只能作为跨 namespace 的“读源”，不能再直接参与 bind。
grep -q '_gfp_proc_source="/proc/1/root$_gfp_source"' "$BRIDGE" ||
    fail '缺少 /proc/1/root 读源路径'
grep -q 'cat "$proc_src" > "$stage"' "$BRIDGE" ||
    fail '模块路径不可见时未复制到 namespace staging 文件'
! grep -q 'for _gfp_src_form in .*proc/1/root' "$BRIDGE" ||
    fail '仍把 /proc/1/root 当作 bind 源兜底'
! grep -q '_gfp_ns_source="/proc/1/root' "$BRIDGE" ||
    fail '仍在无条件把 /proc/1/root 当作 bind 源'

# 2. staging 必须落在目标 namespace 的普通路径，成功后立即清理。
grep -q 'LUOSHU_GOOGLE_FONT_STAGE_DIR:-/data/local/tmp' "$BRIDGE" ||
    fail '缺少目标 namespace staging 目录'
grep -q 'ok:plain' "$BRIDGE" || fail '缺少普通路径成功模式'
grep -q 'ok:staging' "$BRIDGE" || fail '缺少 staging 成功模式'
grep -q 'rm -f "$stage"' "$BRIDGE" || fail 'staging 文件未清理'
grep -q 'chcon --reference="$dst" "$stage"' "$BRIDGE" ||
    fail 'staging 未继承 provider 目标的 SELinux 标签'

# 3. 错误不能按「字体 × PID × 24 次重试」逐条刷屏；一轮只保留汇总与首错。
grep -q '_gfp_ns_first_error=' "$BRIDGE" || fail '缺少 namespace 首错聚合'
grep -q '命名空间=attempted:' "$BRIDGE" || fail '缺少 namespace 挂载汇总'
grep -q '缺源=$_gfp_missing_sources' "$BRIDGE" || fail '缺少源字体未进入汇总'
grep -q '首个挂载错误=' "$BRIDGE" || fail '汇总未包含首个挂载错误'
grep -q '首个缺源=' "$BRIDGE" || fail '汇总未包含首个缺源目标'

sh -n "$BRIDGE"

# 4. 能创建真实 mount namespace 时，验证 staging 文件 bind 后可立即 unlink，
#    destination 仍保持挂载内容；受限 CI/容器优雅跳过。
if ! command -v unshare >/dev/null 2>&1 || ! command -v mount >/dev/null 2>&1; then
    echo 'google_font_provider_mount_test: PASS (跳过 namespace 实测：缺少 unshare/mount)'
    exit 0
fi
if ! unshare -m true 2>/dev/null; then
    echo 'google_font_provider_mount_test: PASS (跳过 namespace 实测：无权限创建 mount namespace)'
    exit 0
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
printf 'REPLACEMENT\n' > "$TMP/src"
printf 'ORIGINAL\n' > "$TMP/dst"
RESULT=$(unshare -m sh -c '
    src="$1"; dst="$2"; stage="$3"
    mount --bind "$src" "$dst" 2>/dev/null || exit 10
    plain=$(cat "$dst" 2>/dev/null)
    umount "$dst" 2>/dev/null || exit 11
    cat "$src" > "$stage" || exit 12
    mount --bind "$stage" "$dst" 2>/dev/null || exit 13
    rm -f "$stage"
    [ ! -e "$stage" ] || exit 14
    staged=$(cat "$dst" 2>/dev/null)
    umount "$dst" 2>/dev/null || exit 15
    printf "plain=%s staged=%s" "$plain" "$staged"
' sh "$TMP/src" "$TMP/dst" "$TMP/stage" 2>/dev/null) || RESULT=""
[ "$RESULT" = 'plain=REPLACEMENT staged=REPLACEMENT' ] ||
    fail "namespace staging bind 行为异常：${RESULT:-empty}"

echo 'google_font_provider_mount_test: PASS'
