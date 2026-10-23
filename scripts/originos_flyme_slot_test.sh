#!/bin/sh
# OriginOS / Flyme 专有字体槽直写：精确槽位写入、保护槽保留、未核实槽只诊断、Latin-only 字体不占 CJK 槽。
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-oem-slot)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE_DIR="$TMP/module"
MODDIR="$MODULE_DIR"
LUOSHU_PUBLIC_DIR="$TMP/public"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
export MODULE_DIR MODDIR LUOSHU_PUBLIC_DIR USER_FONTS_DIR
mkdir -p "$MODULE_DIR/common" "$MODULE_DIR/config" "$MODULE_DIR/system/fonts" "$USER_FONTS_DIR"

make_font() {
    { printf '%s\n' "$2"; dd if=/dev/zero bs=2048 count=1 2>/dev/null; } > "$USER_FONTS_DIR/$1"
}
make_font Demo-Regular.ttf regular-source
make_font Demo-Bold.ttf bold-source

_log_step() { :; }
. "$ROOT/common/util_functions.sh"
. "$ROOT/common/rom_adapters.sh"
. "$ROOT/common/origin_flyme_global.sh"
set -eu

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

# ---- OriginOS ----
OR="$TMP/origin-real"
LUOSHU_TEST_ROM=originos
for v in SYSTEM SYSTEM_EXT PRODUCT VENDOR ODM OEM MY_PRODUCT PRODUCT_VIVO SYSTEM_EXT_VIVO VENDOR_VIVO; do
    eval "LUOSHU_ORIGINOS_${v}_FONTS_ROOT=\"$OR/absent-$v\""
    export "LUOSHU_ORIGINOS_${v}_FONTS_ROOT"
done
LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT="$OR/system/fonts"
export LUOSHU_TEST_ROM LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT
mkdir -p "$LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT"
for n in VivoFont.ttf DroidSansFallbackBBK.ttf DroidSansFallback.ttf VivoSans-Clock.ttf \
         DroidSansMono.ttf NotoColorEmoji.ttf vivoSansThai.ttf VivoIcon.ttf Roboto-Bold.ttf; do
    : > "$LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT/$n"
done

F="$MODULE_DIR/system/fonts"
copy_as_originos "$USER_FONTS_DIR/Demo-Regular.ttf" "$F" quick Demo || fail "copy_as_originos 失败"
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$F/VivoFont.ttf" || fail 'VivoFont.ttf 未写入用户字体'
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$F/DroidSansFallbackBBK.ttf" || fail 'DroidSansFallbackBBK.ttf 未写入'
cmp -s "$USER_FONTS_DIR/Demo-Bold.ttf" "$F/Roboto-Bold.ttf" || fail 'Roboto-Bold 字重不对'
for n in DroidSansFallback.ttf VivoSans-Clock.ttf DroidSansMono.ttf NotoColorEmoji.ttf vivoSansThai.ttf VivoIcon.ttf; do
    test ! -e "$F/$n" || fail "$n 应保留原厂"
done
grep -q '^originos|system/fonts/VivoFont.ttf|' "$MODULE_DIR/config/oem-font-targets.conf" || fail 'manifest 缺 VivoFont'
D="$MODULE_DIR/config/oem-font-diagnostic.conf"
grep -q '^originos|protected|.*/VivoSans-Clock.ttf$' "$D" || fail '时钟槽未记诊断'
grep -q '^originos|protected|.*/VivoIcon.ttf$' "$D" || fail '图标槽未记诊断'
grep -q '^originos|protected|.*/vivoSansThai.ttf$' "$D" || fail '泰文槽未记诊断'

# Latin-only 用户字体：不得占用 CJK 回退槽，Latin 槽照写。
LUOSHU_FONT_HAS_CJK=false
export LUOSHU_FONT_HAS_CJK
copy_as_originos "$USER_FONTS_DIR/Demo-Regular.ttf" "$F" quick Demo || fail "copy_as_originos 失败"
test ! -e "$F/DroidSansFallbackBBK.ttf" || fail 'Latin-only 字体不应写 CJK 槽'
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$F/VivoFont.ttf" || fail 'Latin-only 仍应写 VivoFont'
grep -q '^originos|coverage|.*/DroidSansFallbackBBK.ttf$' "$D" || fail 'CJK 槽跳过未记诊断'
unset LUOSHU_FONT_HAS_CJK
luoshu_oem_clear_managed_fonts
test ! -e "$F/VivoFont.ttf" || fail '清理后 VivoFont 仍存在'

# 精确名匹配：只有完整文件名才算专有槽。
_luoshu_oem_exact_slot_kind originos VivoFontX.ttf >/dev/null 2>&1 && fail '近似名不应命中'
_luoshu_oem_exact_slot_kind flyme VivoFont.ttf >/dev/null 2>&1 && fail '其他 ROM 不应命中 vivo 槽'

# ---- Flyme：SysSans 类未核实，只诊断 ----
FR="$TMP/flyme-real"
LUOSHU_TEST_ROM=flyme
for v in SYSTEM SYSTEM_EXT PRODUCT VENDOR ODM OEM MY_PRODUCT; do
    eval "LUOSHU_FLYME_${v}_FONTS_ROOT=\"$FR/absent-$v\""
    export "LUOSHU_FLYME_${v}_FONTS_ROOT"
done
LUOSHU_FLYME_SYSTEM_FONTS_ROOT="$FR/system/fonts"
LUOSHU_FLYME_DATA_FONT_ROOT="$TMP/absent-data"
export LUOSHU_TEST_ROM LUOSHU_FLYME_SYSTEM_FONTS_ROOT LUOSHU_FLYME_DATA_FONT_ROOT
mkdir -p "$LUOSHU_FLYME_SYSTEM_FONTS_ROOT"
for n in FlymeSans-Regular.ttf FlymeSans-Bold.ttf SysSans-Hans-Regular.ttf FlymeClock.ttf DroidSansMono.ttf; do
    : > "$LUOSHU_FLYME_SYSTEM_FONTS_ROOT/$n"
done
copy_as_flyme "$USER_FONTS_DIR/Demo-Regular.ttf" "$F" quick Demo || fail "copy_as_flyme 失败"
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$F/FlymeSans-Regular.ttf" || fail 'FlymeSans-Regular 未写入'
cmp -s "$USER_FONTS_DIR/Demo-Bold.ttf" "$F/FlymeSans-Bold.ttf" || fail 'FlymeSans-Bold 字重不对'
test ! -e "$F/SysSans-Hans-Regular.ttf" || fail 'Flyme SysSans 未核实，不应替换'
test ! -e "$F/FlymeClock.ttf" || fail 'Flyme 时钟槽应保留'
grep -q '^flyme|unverified|.*/SysSans-Hans-Regular.ttf$' "$D" || fail 'SysSans 未记诊断'
grep -q '^flyme|protected|.*/FlymeClock.ttf$' "$D" || fail 'Flyme 时钟未记诊断'
luoshu_oem_clear_managed_fonts

# 其他 ROM 行为不变：无 vivo/魅族属性时识别为 generic，不进入 OEM 直写。
LUOSHU_TEST_ROM=''
if ! command -v getprop >/dev/null 2>&1; then
    [ "$(_luoshu_oem_detect_rom)" = generic ] || fail '无 ROM 属性时应为 generic'
fi

printf 'OriginOS/Flyme slot tests passed.\n'
