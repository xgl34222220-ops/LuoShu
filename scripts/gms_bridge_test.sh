#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-gms-test)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/LuoShu"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/source"
cp "$ROOT/common/db_engine" "$MOD/common/db_engine"
cp "$ROOT/common/rom_adapters.sh" "$MOD/common/rom_adapters.sh"
cp "$ROOT/common/play_font_bridge" "$MOD/common/play_font_bridge"
BRIDGE_DATA_DIR="$TMP/data-fonts-luoshu"
export BRIDGE_DATA_DIR

for weight in regular medium bold; do
    file="$MOD/source/${weight}.ttf"
    : > "$file"
    while [ "$(wc -c < "$file")" -lt 2048 ]; do
        printf '%s-font-data-0123456789abcdef\n' "$weight" >> "$file"
    done
done

MODDIR="$MOD" MODULE_DIR="$MOD" sh -c '
    . "$MODDIR/common/rom_adapters.sh"
    get_weight_file() {
        case "$2" in
            medium|bold) printf "%s/source/%s.ttf\n" "$MODDIR" "$2" ;;
            *) printf "%s/source/regular.ttf\n" "$MODDIR" ;;
        esac
    }
    _prepare_gms_bridge_sources "$MODDIR/source/regular.ttf" Demo
'

test -s "$MOD/config/gms_bridge/regular.font"
test -s "$MOD/config/gms_bridge/medium.font"
test -s "$MOD/config/gms_bridge/bold.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve GoogleSans-Regular.ttf)" = "$MOD/config/gms_bridge/regular.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve GoogleSans-Medium.ttf)" = "$MOD/config/gms_bridge/medium.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve GoogleSans-Bold.ttf)" = "$MOD/config/gms_bridge/bold.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve Google_Sans_Flex-400-100_0-0_0.ttf)" = "$MOD/config/gms_bridge/regular.font"

# 真可变字体存在时仍优先使用 variable.font，而不是静态兼容源。
cp "$MOD/source/regular.ttf" "$MOD/config/gms_bridge/variable.font"
printf 'fvar' >> "$MOD/config/gms_bridge/variable.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve Google_Sans_Flex-400-100_0-0_0.ttf)" = "$MOD/config/gms_bridge/variable.font"
test -z "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve Google_Sans_Code-400.ttf || true)"

# 稳定桥接源必须位于模块目录之外，以绕过 HyperOS 应用命名空间隔离。
MODDIR="$MOD" BRIDGE_DATA_DIR="$BRIDGE_DATA_DIR" sh "$MOD/common/play_font_bridge" now >/dev/null 2>&1 || true
test -s "$BRIDGE_DATA_DIR/regular.font"
test -s "$BRIDGE_DATA_DIR/medium.font"
test -s "$BRIDGE_DATA_DIR/bold.font"
test -s "$BRIDGE_DATA_DIR/variable.font"

# HyperOS 不再把 root 可读等同于 GMS 可读：禁用 FontsProvider 与更新器，
# 让 Play 回退到已经替换的系统 sans-serif；恢复时还原组件原始状态。
MOCK_BIN="$TMP/mock-bin"
MOCK_LOG="$TMP/mock.log"
GLOBAL_STATE_DIR="$TMP/global-state"
mkdir -p "$MOCK_BIN"
cat > "$MOCK_BIN/getprop" <<'EOF'
#!/bin/sh
[ "$1" = "ro.mi.os.version.name" ] && echo OS3.0
EOF
cat > "$MOCK_BIN/cmd" <<'EOF'
#!/bin/sh
case "$*" in
    *get-component-enabled-setting*) echo default ;;
esac
exit 0
EOF
cat > "$MOCK_BIN/pm" <<'EOF'
#!/bin/sh
echo "pm $*" >> "$MOCK_LOG"
exit 0
EOF
cat > "$MOCK_BIN/am" <<'EOF'
#!/bin/sh
echo "am $*" >> "$MOCK_LOG"
exit 0
EOF
chmod 755 "$MOCK_BIN"/*
export MOCK_LOG GLOBAL_STATE_DIR
: > "$MOCK_LOG"
PATH="$MOCK_BIN:$PATH" MODDIR="$MOD" GLOBAL_STATE_DIR="$GLOBAL_STATE_DIR" \
    BRIDGE_DATA_DIR="$BRIDGE_DATA_DIR" sh "$MOD/common/play_font_bridge" boot
grep -q 'pm disable --user 0 com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider' "$MOCK_LOG"
grep -q 'pm disable --user 0 com.google.android.gms/com.google.android.gms.fonts.update.UpdateSchedulerService' "$MOCK_LOG"
grep -q 'am force-stop com.android.vending' "$MOCK_LOG"
! grep -q 'am force-stop com.google.android.gms' "$MOCK_LOG"
grep -q '^mode=hyperos-system-fallback$' "$MOD/config/gms_bridge/runtime.status"
test -s "$GLOBAL_STATE_DIR/gms_font_components.conf"

PATH="$MOCK_BIN:$PATH" MODDIR="$MOD" GLOBAL_STATE_DIR="$GLOBAL_STATE_DIR" \
    BRIDGE_DATA_DIR="$BRIDGE_DATA_DIR" sh "$MOD/common/play_font_bridge" restore
grep -q 'pm default-state --user 0 com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider' "$MOCK_LOG"
grep -q 'pm default-state --user 0 com.google.android.gms/com.google.android.gms.fonts.update.UpdateSchedulerService' "$MOCK_LOG"
test ! -e "$GLOBAL_STATE_DIR/gms_font_components.conf"

echo "GMS bridge tests passed."
