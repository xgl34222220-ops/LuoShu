#!/bin/sh
# Legacy mapper + capability layer, with generated fonts:
#   - a variable user font fills static 100-900 slots with real wght instances
#     while MiSansVF keeps its fvar axes;
#   - a static family maps by OS/2 weight, nearest weight for missing ones, and
#     an italic face never lands in an upright slot;
#   - generic italic slots stay stock without a user italic face;
#   - NotoColorEmoji is never overwritten by a text font; Serif/Emoji slots are
#     only written when the user enabled them;
#   - ZIP import splits a TTC by face and an all-colour collection is rejected
#     with an explicit reason.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='字体能力映射'
assert_eq() { [ "$1" = "$2" ] || fail "$3（实际 '$1'，期望 '$2'）"; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
FIX="python3 $ROOT/scripts/font_capability_fixtures.py"
python3 -c 'import fontTools' 2>/dev/null || { echo 'font capability mapping test skipped: fontTools unavailable'; exit 0; }

STOCK="$TMP/stock"
mkdir -p "$STOCK" "$TMP/fonts-vf" "$TMP/fonts-static" "$TMP/emoji"
for name in MiSansVF.ttf 100.ttf 400.ttf 700.ttf Roboto-Thin.ttf Roboto-Regular.ttf Roboto-Bold.ttf \
            Roboto-ExtraBold.ttf Roboto-Italic.ttf Roboto-BoldItalic.ttf NotoColorEmoji.ttf \
            NotoSerif-Regular.ttf NotoSerif-Bold.ttf NotoSerif-Italic.ttf MiSerifSCVF.ttf; do
    printf 'stock-%s' "$name" > "$STOCK/$name"
done

$FIX variable "$TMP/fonts-vf/Demo-Variable.ttf" --family DemoVF
$FIX static "$TMP/fonts-static/Demo-Regular.ttf" --style Regular --weight 400
$FIX static "$TMP/fonts-static/Demo-Bold.ttf" --style Bold --weight 700
$FIX static "$TMP/fonts-static/Demo-Italic.ttf" --style Italic --weight 400 --italic
$FIX static "$TMP/emoji/Party.ttf" --family Party --color

weight_of() {
    python3 - "$1" <<'PY'
import sys
from fontTools.ttLib import TTFont
with TTFont(sys.argv[1]) as font:
    flags = []
    if "fvar" in font:
        flags.append("fvar")
    if int(font["OS/2"].fsSelection) & 1:
        flags.append("italic")
    print(font["OS/2"].usWeightClass, *flags)
PY
}

run_mapper() {
    # $1 dest, $2 user font dir, $3 source, $4 family, $5 rom (hyperos|generic), $6 slot options conf
    (
        set +eu
        LUOSHU_REAL_MODDIR="$ROOT"; LUOSHU_CAPABILITY_PYTHON=python3
        LUOSHU_SLOT_OPTIONS_CONF="$6"; LUOSHU_SLOT_OPTIONS_ROOTS="$STOCK"
        export LUOSHU_REAL_MODDIR LUOSHU_CAPABILITY_PYTHON LUOSHU_SLOT_OPTIONS_CONF LUOSHU_SLOT_OPTIONS_ROOTS
        . "$ROOT/common/legacy_v14_4/util_functions.sh" >/dev/null 2>&1
        . "$ROOT/common/legacy_v14_4/rom_adapters.sh"
        USER_FONTS_DIR="$2"
        _rom_exact_target_exists() { [ -e "$STOCK/$1" ]; }
        if [ "$5" = hyperos ]; then IS_HYPEROS=true IS_COLOROS=false; else IS_HYPEROS=false IS_COLOROS=false; fi
        mkdir -p "$1"
        apply_font_by_rom "$3" "$1" quick "$4"
    ) > "$TMP/log" 2>&1 || { cat "$TMP/log" >&2; fail "apply_font_by_rom 失败（$5）"; }
}

# 1. Variable user font on HyperOS.
D1="$TMP/stage1/system/fonts"
run_mapper "$D1" "$TMP/fonts-vf" "$TMP/fonts-vf/Demo-Variable.ttf" Demo-Variable hyperos "$TMP/none.conf"
assert_eq "$(weight_of "$D1/700.ttf")" "700" "700.ttf 必须是 wght=700 静态实例"
assert_eq "$(weight_of "$D1/100.ttf")" "100" "100.ttf 必须是 wght=100 静态实例"
assert_eq "$(weight_of "$D1/400.ttf")" "400" "400.ttf 必须是静态实例"
assert_eq "$(weight_of "$D1/Roboto-ExtraBold.ttf")" "800" "Roboto-ExtraBold 必须映射 800 而非 700"
assert_eq "$(weight_of "$D1/Roboto-Thin.ttf")" "100" "Roboto-Thin 必须映射 100"
case "$(weight_of "$D1/MiSansVF.ttf")" in *fvar*) ;; *) fail 'MiSansVF 必须保留 fvar 轴';; esac
[ ! -e "$D1/NotoColorEmoji.ttf" ] || fail 'Emoji 槽不能被文字字体覆盖'
[ ! -e "$D1/NotoSerif-Regular.ttf" ] || fail '未启用衬线槽时衬线保持原厂'

# 2. Static family with an italic member on HyperOS: OS/2 weights + nearest.
D2="$TMP/stage2/system/fonts"
run_mapper "$D2" "$TMP/fonts-static" "$TMP/fonts-static/Demo-Regular.ttf" Demo hyperos "$TMP/none.conf"
assert_eq "$(weight_of "$D2/400.ttf")" "400" "400.ttf 必须是正体 Regular（不能是斜体）"
assert_eq "$(weight_of "$D2/Roboto-Regular.ttf")" "400" "Roboto-Regular 必须是正体"
assert_eq "$(weight_of "$D2/700.ttf")" "700" "700.ttf 必须是 Bold"
assert_eq "$(weight_of "$D2/Roboto-ExtraBold.ttf")" "700" "缺 800 时就近映射到 Bold，而不是 Regular"
assert_eq "$(weight_of "$D2/100.ttf")" "400" "缺 100 时就近映射到 Regular"

# 3. Generic ROM: italic slots stay stock without an italic face; take the italic face when present.
mkdir -p "$TMP/fonts-upright"
cp "$TMP/fonts-static/Demo-Regular.ttf" "$TMP/fonts-static/Demo-Bold.ttf" "$TMP/fonts-upright/"
D3="$TMP/stage3/system/fonts"
run_mapper "$D3" "$TMP/fonts-upright" "$TMP/fonts-upright/Demo-Regular.ttf" Demo generic "$TMP/none.conf"
[ ! -e "$D3/Roboto-Italic.ttf" ] || fail '用户无斜体时 Roboto-Italic 必须保持原厂'
[ ! -e "$D3/Roboto-BoldItalic.ttf" ] || fail '用户无斜体时 Roboto-BoldItalic 必须保持原厂'
assert_eq "$(weight_of "$D3/Roboto-Bold.ttf")" "700" "通用 ROM 的 Roboto-Bold 必须是 Bold，而不是 Regular"
D4="$TMP/stage4/system/fonts"
run_mapper "$D4" "$TMP/fonts-static" "$TMP/fonts-static/Demo-Regular.ttf" Demo generic "$TMP/none.conf"
assert_eq "$(weight_of "$D4/Roboto-Italic.ttf")" "400 italic" "Roboto-Italic 必须来自用户斜体字体面"
assert_eq "$(weight_of "$D4/Roboto-Regular.ttf")" "400" "Roboto-Regular 必须是正体"

# 4. Emoji guard on the alias primitive itself.
(
    set +eu
    LUOSHU_REAL_MODDIR="$ROOT"; export LUOSHU_REAL_MODDIR
    . "$ROOT/common/legacy_v14_4/rom_adapters.sh"
    _font_alias "$TMP/fonts-static/Demo-Regular.ttf" "$TMP/NotoColorEmoji.ttf" 2>/dev/null && exit 1
    [ ! -e "$TMP/NotoColorEmoji.ttf" ]
) || fail '_font_alias 必须拒绝写入 Emoji 槽位'

# 5. Optional Serif / Emoji slots, only when enabled.
CONF="$TMP/slot.conf"
printf 'serif=Demo\nemoji=%s\n' "$TMP/emoji/Party.ttf" > "$CONF"
D5="$TMP/stage5/system/fonts"
run_mapper "$D5" "$TMP/fonts-upright" "$TMP/fonts-upright/Demo-Regular.ttf" Demo hyperos "$CONF"
cmp -s "$D5/NotoColorEmoji.ttf" "$TMP/emoji/Party.ttf" || fail '启用后 Emoji 槽必须使用用户 Emoji 字体'
assert_eq "$(weight_of "$D5/NotoSerif-Bold.ttf")" "700" "衬线 Bold 槽必须映射用户 Bold"
assert_eq "$(weight_of "$D5/NotoSerif-Regular.ttf")" "400" "衬线 Regular 槽必须映射用户 Regular"
[ ! -e "$D5/NotoSerif-Italic.ttf" ] || fail '衬线斜体槽保持原厂'
[ ! -e "$D5/MiSerifSCVF.ttf" ] || fail '缺汉字的衬线字体不能替换中文衬线槽'

# 6. Slot option CLI rejects a non-colour emoji font.
OUT=$(LUOSHU_REAL_MODDIR="$ROOT" LUOSHU_CAPABILITY_PYTHON=python3 LUOSHU_SLOT_OPTIONS_CONF="$TMP/cli.conf" \
    sh "$ROOT/common/font_slot_options.sh" set-emoji "$TMP/fonts-static/Demo-Regular.ttf" || true)
printf '%s' "$OUT" | grep -q '不是彩色 Emoji 字体' || fail "非彩色字体必须被拒绝：$OUT"
OUT=$(LUOSHU_REAL_MODDIR="$ROOT" LUOSHU_CAPABILITY_PYTHON=python3 LUOSHU_SLOT_OPTIONS_CONF="$TMP/cli.conf" \
    sh "$ROOT/common/font_slot_options.sh" set-emoji "$TMP/emoji/Party.ttf")
printf '%s' "$OUT" | grep -q '"status":"ok"' || fail "彩色 Emoji 字体应可启用：$OUT"
grep -q "^emoji=$TMP/emoji/Party.ttf\$" "$TMP/cli.conf" || fail 'Emoji 设置未写入'
LUOSHU_REAL_MODDIR="$ROOT" LUOSHU_SLOT_OPTIONS_CONF="$TMP/cli.conf" sh "$ROOT/common/font_slot_options.sh" clear-emoji >/dev/null
! grep -q '^emoji=' "$TMP/cli.conf" || fail '清除 Emoji 设置失败'

# 7. ZIP import: a TTC is split by face into one family; an all-colour TTC is rejected with a reason.
$FIX static "$TMP/r.ttf" --family Coll --style Regular --weight 400
$FIX static "$TMP/b.ttf" --family Coll --style Bold --weight 700
$FIX static "$TMP/e.ttf" --family Coll --color
mkdir -p "$TMP/zipsrc" "$TMP/zipbad" "$TMP/public/import" "$TMP/public/fonts" "$TMP/cache"
$FIX collection "$TMP/zipsrc/Coll.ttc" --members "$TMP/r.ttf" "$TMP/b.ttf"
$FIX collection "$TMP/zipbad/Emoji.otc" --members "$TMP/e.ttf" "$TMP/e.ttf"
printf 'name=集合字体\n' > "$TMP/zipsrc/module.prop"
(cd "$TMP/zipsrc" && python3 -c 'import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],"w"); [z.write(n) for n in ("Coll.ttc","module.prop")]; z.close()' "$TMP/public/import/coll.zip")
(cd "$TMP/zipbad" && python3 -c 'import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],"w"); z.write("Emoji.otc"); z.close()' "$TMP/public/import/bad.zip")
command -v unzip >/dev/null 2>&1 || command -v busybox >/dev/null 2>&1 || {
    echo 'font capability mapping test: ZIP part skipped (no unzip)'; echo '字体能力映射测试通过'; exit 0; }
zip_import() {
    sh -c '
        set -eu
        MODDIR="$1"; MODULE_DIR="$1"
        LUOSHU_PUBLIC_DIR="$2/public"; USER_FONTS_DIR="$2/public/fonts"
        USER_IMPORT_DIR="$2/public/import"; IMPORT_CACHE_DIR="$2/cache"
        LUOSHU_IMPORT_PYTHON=python3
        export LUOSHU_IMPORT_PYTHON
        json_escape() { printf "%s" "$1" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g" | tr "\n\r" "  "; }
        . "$1/common/util_functions.sh"
        . "$1/common/font_check.sh"
        . "$1/common/font_import.sh"
        . "$1/common/font_import_compat.sh"
        import_zip_package "$3"
    ' sh "$ROOT" "$TMP" "$1"
}
OUT=$(zip_import coll.zip)
printf '%s\n' "$OUT" | grep -q '"status":"ok"' || fail "TTC ZIP 导入失败：$OUT"
printf '%s\n' "$OUT" | grep -q '"mode":"family"' || fail "TTC 字体面应组成同一字体族：$OUT"
ls "$TMP/public/fonts" | grep -q -- '-Bold\.ttf$' || fail 'TTC 的 Bold 字体面未按字重导入'
! ls "$TMP/public/fonts" | grep -qi '\.ttc$' || fail '字体库中不应再保存整份 TTC'
OUT=$(zip_import bad.zip)
printf '%s\n' "$OUT" | grep -q 'TTC/OTC 字体集合无法导入' || fail "不支持的集合必须明确拒绝：$OUT"

echo '字体能力映射测试通过'
