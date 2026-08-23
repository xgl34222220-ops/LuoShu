#!/bin/sh
# 两个 ROM 适配器的发现能力必须对等。ColorOS 会真的枚举分区里的字体文件、再按前缀挑出 OEM 的
# UI 家族；HyperOS 此前只有五个写死的 MiSans 名字，唯一的枚举只覆盖 Roboto/GoogleSans 和时钟槽。
# 于是 ROM 里任何一个不在那五个名字里的 MiSans 变体全部漏掉，表现就是「同一份字体，红米很多
# 地方没换，一加正常」。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

mk() { mkdir -p "$(dirname "$1")"; : > "$1"; }

CASE='HyperOS 枚举真实分区里的 MiSans 家族'
HFONTS="$TMP/hyper/system/fonts"
for n in MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf \
         MiSansTextVF.ttf MiSansRoundedVF.ttf MiSansGlobalVF.ttf MiSansJPVF.ttf MiLanProVF.ttf \
         MiSansVF_HK.ttf Roboto-Regular.ttf; do mk "$HFONTS/$n"; done
# 这几个必须保持原厂
for n in MiSansSerifVF.ttf MiSansMonoVF.ttf MitypeClock.ttf NotoColorEmoji.ttf MiSansVF-Italic.ttf; do
    mk "$HFONTS/$n"
done

OUT="$TMP/hyper.out"
sh -c '
MODULE_DIR="'"$TMP"'/hyper/module"; MODDIR="$MODULE_DIR"
LUOSHU_SYSTEM_FONTS_ROOT="'"$HFONTS"'"
LUOSHU_PRODUCT_FONTS_ROOT="'"$TMP"'/none1"
LUOSHU_SYSTEM_EXT_FONTS_ROOT="'"$TMP"'/none2"
LUOSHU_MI_EXT_FONTS_ROOT="'"$TMP"'/none3"
export MODULE_DIR MODDIR LUOSHU_SYSTEM_FONTS_ROOT LUOSHU_PRODUCT_FONTS_ROOT LUOSHU_SYSTEM_EXT_FONTS_ROOT LUOSHU_MI_EXT_FONTS_ROOT
. "'"$ROOT"'/common/hyperos_global.sh" 2>/dev/null
_hyperos_discovered_ui_files
' > "$OUT" 2>/dev/null

for n in MiSansTextVF.ttf MiSansRoundedVF.ttf MiSansGlobalVF.ttf MiSansJPVF.ttf MiLanProVF.ttf MiSansVF_HK.ttf; do
    ok grep -qx "$n" "$OUT"
done
ok grep -qx MiSansL3.otf "$OUT"

CASE='受保护的字面不得被 HyperOS 枚举带走'
for n in MiSansSerifVF.ttf MiSansMonoVF.ttf MitypeClock.ttf NotoColorEmoji.ttf MiSansVF-Italic.ttf; do
    no grep -qx "$n" "$OUT"
done

CASE='枚举结果必须进入 get_all_hyperos_files'
ALL="$TMP/hyper.all"
sh -c '
MODULE_DIR="'"$TMP"'/hyper/module"; MODDIR="$MODULE_DIR"
LUOSHU_SYSTEM_FONTS_ROOT="'"$HFONTS"'"
LUOSHU_PRODUCT_FONTS_ROOT="'"$TMP"'/none1"
LUOSHU_SYSTEM_EXT_FONTS_ROOT="'"$TMP"'/none2"
LUOSHU_MI_EXT_FONTS_ROOT="'"$TMP"'/none3"
export MODULE_DIR MODDIR LUOSHU_SYSTEM_FONTS_ROOT LUOSHU_PRODUCT_FONTS_ROOT LUOSHU_SYSTEM_EXT_FONTS_ROOT LUOSHU_MI_EXT_FONTS_ROOT
. "'"$ROOT"'/common/hyperos_global.sh" 2>/dev/null
get_all_hyperos_files | tr " " "\n"
' > "$ALL" 2>/dev/null
ok grep -qx MiSansRoundedVF.ttf "$ALL"
ok grep -qx MiLanProVF.ttf "$ALL"

CASE='ColorOS 枚举必须同时覆盖 .otf'
CFONTS="$TMP/coloros/system/fonts"
for n in SysFont-Regular.ttf OplusSans-Regular.otf OSans-Ext-Regular.otf OPSans-En-Medium.ttf \
         GoogleSansText-Regular.ttf NotoSerif-Regular.ttf DroidSansMono.ttf; do mk "$CFONTS/$n"; done
COUT="$TMP/coloros.out"
sh -c '
MODULE_DIR="'"$TMP"'/coloros/module"; MODDIR="$MODULE_DIR"
LUOSHU_COLOROS_SYSTEM_FONTS_ROOT="'"$CFONTS"'"
LUOSHU_COLOROS_PRODUCT_FONTS_ROOT="'"$TMP"'/cnone1"
LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT="'"$TMP"'/cnone2"
LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT="'"$TMP"'/cnone3"
export MODULE_DIR MODDIR LUOSHU_COLOROS_SYSTEM_FONTS_ROOT LUOSHU_COLOROS_PRODUCT_FONTS_ROOT LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT
. "'"$ROOT"'/common/coloros_global.sh" 2>/dev/null
_coloros_discovered_ui_files
' > "$COUT" 2>/dev/null
ok grep -qx OplusSans-Regular.otf "$COUT"
ok grep -qx OSans-Ext-Regular.otf "$COUT"
ok grep -qx SysFont-Regular.ttf "$COUT"
no grep -qx NotoSerif-Regular.ttf "$COUT"
no grep -qx DroidSansMono.ttf "$COUT"

CASE='源码契约：两边都必须有枚举函数'
ok grep -q '_hyperos_discovered_ui_files()' "$ROOT/common/hyperos_global.sh"
ok grep -q '_coloros_discovered_ui_files()' "$ROOT/common/coloros_global.sh"

printf 'ROM adapter discovery parity tests passed.\n'
