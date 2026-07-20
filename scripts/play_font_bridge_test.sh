#!/bin/sh
set -eu
REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT HUP INT TERM

MODDIR="$ROOT/module"
DATA_ROOT="$ROOT/data"
PM_LOG="$ROOT/pm.log"
FAKE_PM="$ROOT/fake-pm"
mkdir -p "$MODDIR/config" "$MODDIR/logs" \
    "$DATA_ROOT/user/0/com.google.android.gms/files/fonts/opentype" \
    "$DATA_ROOT/user/10/com.google.android.gms/files/fonts/opentype"
printf 'cached\n' > "$DATA_ROOT/user/0/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"
printf 'cached\n' > "$DATA_ROOT/user/10/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"

cat > "$MODDIR/config/play_font_bridge.conf" <<'EOF_STATE'
version=2
0|com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider|default
0|com.google.android.gms/com.google.android.gms.fonts.update.UpdateSchedulerService|default
10|com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider|default
10|com.google.android.gms/com.google.android.gms.fonts.update.UpdateSchedulerService|default
EOF_STATE

cat > "$FAKE_PM" <<'EOF_PM'
#!/bin/sh
printf '%s\n' "$*" >> "$LUOSHU_PM_LOG"
case "$1" in
    path) printf 'package:/system/priv-app/GmsCore/GmsCore.apk\n' ;;
    default-state)
        printf 'Component %s new state: default\n' "${4:-unknown}"
        ;;
    enable)
        printf 'Component %s new state: enabled\n' "${4:-unknown}"
        ;;
    *) exit 0 ;;
esac
EOF_PM
chmod +x "$FAKE_PM"

# service.sh 仍调用 apply；新版 apply 必须迁移并恢复旧测试状态，而不是再次禁用组件。
_result=$(MODDIR="$MODDIR" \
LUOSHU_DATA_ROOT="$DATA_ROOT" \
LUOSHU_PM="$FAKE_PM" \
LUOSHU_DUMPSYS=/bin/false \
LUOSHU_PM_LOG="$PM_LOG" \
sh "$REPO_ROOT/common/play_font_bridge" apply)

test "$_result" = 'restored=4'
test ! -e "$MODDIR/config/play_font_bridge.conf"
test "$(grep -c 'default-state --user' "$PM_LOG")" -eq 4
! grep -qE '(^| )(disable|disable-user)( |$)' "$PM_LOG"

# GMS 的下载字体和 EmojiCompat 缓存必须保留，不能再由洛书删除。
test -f "$DATA_ROOT/user/0/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"
test -f "$DATA_ROOT/user/10/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"
! grep -q 'rm -rf' "$REPO_ROOT/common/play_font_bridge"
! grep -q '/data/fonts' "$REPO_ROOT/common/play_font_bridge"

# 没有旧状态时应保持 Provider 原样，重复执行也必须是幂等的。
_result=$(MODDIR="$MODDIR" \
LUOSHU_PM="$FAKE_PM" \
LUOSHU_DUMPSYS=/bin/false \
LUOSHU_PM_LOG="$PM_LOG" \
sh "$REPO_ROOT/common/play_font_bridge" apply)
test "$_result" = 'provider-preserved'
test "$(grep -c 'default-state --user' "$PM_LOG")" -eq 4
printf 'GMS font provider preservation tests passed.\n'
