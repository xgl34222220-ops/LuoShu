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
    "$DATA_ROOT/user/10/com.google.android.gms/files/fonts/opentype" \
    "$DATA_ROOT/user_de/10/com.google.android.gms/files/fonts/opentype"
printf 'cached\n' > "$DATA_ROOT/user/0/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"
printf 'cached\n' > "$DATA_ROOT/user/10/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"
printf 'cached\n' > "$DATA_ROOT/user_de/10/com.google.android.gms/files/fonts/opentype/GoogleSans.ttf"

cat > "$FAKE_PM" <<'EOF_PM'
#!/bin/sh
printf '%s\n' "$*" >> "$LUOSHU_PM_LOG"
case "$1" in
    path) printf 'package:/system/priv-app/GmsCore/GmsCore.apk\n' ;;
    disable|disable-user)
        printf 'Component %s new state: disabled\n' "${4:-unknown}"
        ;;
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

MODDIR="$MODDIR" \
LUOSHU_DATA_ROOT="$DATA_ROOT" \
LUOSHU_USER_LIST='0 10' \
LUOSHU_PM="$FAKE_PM" \
LUOSHU_DUMPSYS=/bin/false \
LUOSHU_PM_LOG="$PM_LOG" \
sh "$REPO_ROOT/common/play_font_bridge" apply >/dev/null

test ! -d "$DATA_ROOT/user/0/com.google.android.gms/files/fonts"
test ! -d "$DATA_ROOT/user/10/com.google.android.gms/files/fonts"
test ! -d "$DATA_ROOT/user_de/10/com.google.android.gms/files/fonts"
test -f "$MODDIR/config/play_font_bridge.conf"
test "$(grep -c 'disable --user' "$PM_LOG")" -eq 4
test "$(grep -c '|default$' "$MODDIR/config/play_font_bridge.conf")" -eq 4
! grep -q '/data/fonts' "$REPO_ROOT/common/play_font_bridge"

MODDIR="$MODDIR" \
LUOSHU_DATA_ROOT="$DATA_ROOT" \
LUOSHU_USER_LIST='0 10' \
LUOSHU_PM="$FAKE_PM" \
LUOSHU_DUMPSYS=/bin/false \
LUOSHU_PM_LOG="$PM_LOG" \
sh "$REPO_ROOT/common/play_font_bridge" restore >/dev/null

test ! -e "$MODDIR/config/play_font_bridge.conf"
test "$(grep -c 'default-state --user' "$PM_LOG")" -eq 4
printf 'GMS downloadable font bridge tests passed.\n'
