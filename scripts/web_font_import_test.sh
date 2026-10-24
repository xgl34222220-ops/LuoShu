#!/bin/sh
# WOFF/WOFF2 解包与 ZIP 安全解压回归测试。
#   LUOSHU_TEST_WOFF2_DECODER=/path/decoder  使用指定 WOFF2 解码器（例如 qemu 包装的 ARM64 产物）
#   LUOSHU_WOFF2_TEST_BUILD=1                 用固定上游源码为宿主机构建解码器
# 两者都没有时跳过需要解码器的 WOFF2 用例，其余用例照常执行。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

FONT=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
if [ ! -s "$FONT" ]; then
    echo 'Web font import test skipped: DejaVu Sans is unavailable.'
    exit 0
fi
SITE="$ROOT/common/python/lib/python3.14/site-packages"
PYTHONPATH="$SITE"; LUOSHU_IMPORT_PYTHON=python3
export PYTHONPATH LUOSHU_IMPORT_PYTHON
CONV="$ROOT/common/font_web_convert.py"
ZX="$ROOT/common/font_zip_extract.py"
fail() { echo "FAIL: $*" >&2; exit 1; }

mkdir -p "$TMP/src" "$TMP/out"
cp "$FONT" "$TMP/src/Plain.ttf"

# ---- 用 FontTools 生成 WOFF（zlib，无需 Brotli）---------------------------------
python3 -S - "$TMP/src/Plain.ttf" "$TMP/src/Sample.woff" <<'PY'
import sys
from fontTools.ttLib import TTFont
f = TTFont(sys.argv[1]); f.flavor = 'woff'; f.save(sys.argv[2])
PY

same_tables() {
    python3 -S - "$1" "$2" <<'PY'
import sys
from fontTools.ttLib import TTFont
a, b = TTFont(sys.argv[1]), TTFont(sys.argv[2])
assert b.flavor is None, b.flavor
assert sorted(a.keys()) == sorted(b.keys()), (sorted(a.keys()), sorted(b.keys()))
for tag in a.reader.keys():
    if tag == 'head':
        continue  # checkSumAdjustment may differ
    assert a.reader[tag] == b.reader[tag], tag
PY
}

# 1. 自写 WOFF 1.0 解包（关闭 FontTools 路径）
OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 python3 -S "$CONV" "$TMP/src/Sample.woff" "$TMP/out")
printf '%s\n' "$OUT" | grep -q '"ok":true' || fail "native woff: $OUT"
printf '%s\n' "$OUT" | grep -q '"method":"zlib"' || fail "native woff method: $OUT"
printf '%s\n' "$OUT" | grep -q '"format":"TTF"' || fail "native woff format: $OUT"
test -s "$TMP/out/Sample.ttf" || fail 'native woff output missing'
same_tables "$TMP/src/Plain.ttf" "$TMP/out/Sample.ttf"
ls -A "$TMP/out" | grep -q '\.part$' && fail 'temporary file left behind'

# 2. FontTools 优先路径；同名输出不覆盖
OUT=$(python3 -S "$CONV" "$TMP/src/Sample.woff" "$TMP/out")
printf '%s\n' "$OUT" | grep -q '"method":"fonttools"' || fail "fonttools woff: $OUT"
test -s "$TMP/out/Sample-2.ttf" || fail 'collision rename missing'
same_tables "$TMP/src/Plain.ttf" "$TMP/out/Sample-2.ttf"

# 3. 损坏的 WOFF：截断、长度不符、非 WOFF
head -c 3000 "$TMP/src/Sample.woff" > "$TMP/src/Broken.woff"
for f in "$TMP/src/Broken.woff" "$TMP/src/Plain.ttf"; do
    rc=0; OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 python3 -S "$CONV" "$f" "$TMP/out") || rc=$?
    test "$rc" -eq 1 || fail "expected failure for $f"
    printf '%s\n' "$OUT" | grep -q '"ok":false' || fail "no error json for $f: $OUT"
done
python3 - "$TMP/src/Sample.woff" "$TMP/src/BadDir.woff" <<'PY'
import struct, sys
d = bytearray(open(sys.argv[1], 'rb').read())
# 把第一张表的偏移指到文件外
struct.pack_into('>I', d, 44 + 4, len(d) + 64)
open(sys.argv[2], 'wb').write(d)
PY
OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 python3 -S "$CONV" "$TMP/src/BadDir.woff" "$TMP/out" || true)
printf '%s\n' "$OUT" | grep -q 'WOFF 表数据越界' || fail "bad directory not rejected: $OUT"

# ---- font_check.sh：font_validate 原文案不变，font_prepare_import 解包后校验 -----------
RES=$(sh -c '
    MODULE_DIR="$1"; . "$1/common/font_check.sh"
    font_validate "$2" text && echo validate-ok || echo "validate:$FONT_CHECK_ERROR"
    font_prepare_import "$2" "$3/prep" text && echo "prep:$FONT_PREPARED_FROM:$FONT_CHECK_FORMAT:$FONT_PREPARED_PATH" || echo "prepfail:$FONT_CHECK_ERROR"
    font_prepare_import "$4" "$3/prep" text && echo "plain:$FONT_PREPARED_PATH" || echo plainfail
' sh "$ROOT" "$TMP/src/Sample.woff" "$TMP" "$TMP/src/Plain.ttf")
printf '%s\n' "$RES" | grep -qx 'validate:检测到网页字体 WOFF，不能仅修改扩展名后作为系统字体' || fail "validate message changed: $RES"
printf '%s\n' "$RES" | grep -q "^prep:WOFF:TTF:$TMP/prep/Sample.ttf$" || fail "prepare: $RES"
printf '%s\n' "$RES" | grep -qx "plain:$TMP/src/Plain.ttf" || fail "plain prepare: $RES"

# 转换失败时保持原报错文案
cp "$TMP/src/BadDir.woff" "$TMP/src/Bad.woff"
RES=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 sh -c '
    MODULE_DIR="$1"; . "$1/common/font_check.sh"
    font_prepare_import "$2" "$3/prep2" text && echo unexpected || echo "msg:$FONT_CHECK_ERROR|reason:$FONT_WEB_REASON"
' sh "$ROOT" "$TMP/src/Bad.woff" "$TMP")
printf '%s\n' "$RES" | grep -q '^msg:检测到网页字体 WOFF，不能仅修改扩展名后作为系统字体|reason:WOFF 表数据越界$' || fail "failure message: $RES"

# CLI
CLI=$(sh "$ROOT/common/font_check.sh" "$TMP/src/Sample.woff")
printf '%s\n' "$CLI" | grep -q '状态: 通过' || fail "cli: $CLI"
printf '%s\n' "$CLI" | grep -q '原始格式: WOFF' || fail "cli source: $CLI"
CLI=$(sh "$ROOT/common/font_check.sh" --json "$TMP/src/Sample.woff")
printf '%s\n' "$CLI" | grep -q '"valid":true,"format":"TTF","source":"WOFF"' || fail "cli json: $CLI"
CLI=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 sh "$ROOT/common/font_check.sh" "$TMP/src/Bad.woff" || true)
printf '%s\n' "$CLI" | grep -q '原因: 检测到网页字体 WOFF，不能仅修改扩展名后作为系统字体' || fail "cli failure: $CLI"
CLI=$(sh "$ROOT/common/font_check.sh" "$TMP/src/Plain.ttf" || true)
printf '%s\n' "$CLI" | grep -q '真实格式: TTF' || fail "cli plain: $CLI"

# ---- ZIP 安全解压 ---------------------------------------------------------------
python3 - "$TMP" "$TMP/src/Plain.ttf" "$TMP/src/Sample.woff" <<'PY'
import os, stat, sys, zipfile
tmp, ttf, woff = sys.argv[1:4]
data, wdata = open(ttf, 'rb').read(), open(woff, 'rb').read()
def mk(name, entries):
    with zipfile.ZipFile(os.path.join(tmp, name), 'w', zipfile.ZIP_DEFLATED) as z:
        for e in entries:
            if isinstance(e, zipfile.ZipInfo):
                z.writestr(e, b'Plain.ttf')
            else:
                z.writestr(*e)
mk('good.zip', [('a/Plain.ttf', data), ('b/Plain.ttf', data), ('fonts/Web.woff', wdata),
                ('readme.txt', b'x'), ('install.sh', b'rm -rf /'), ('__MACOSX/a/._Plain.ttf', b'junk'),
                ('a/._Hidden.ttf', b'junk')])
mk('slip.zip', [('../evil.ttf', data)])
mk('abs.zip', [('/etc/evil.ttf', data)])
mk('ctrl.zip', [('bad\nname.ttf', data)])
link = zipfile.ZipInfo('link.ttf'); link.create_system = 3
link.external_attr = (stat.S_IFLNK | 0o777) << 16
mk('link.zip', [link])
mk('many.zip', [('f%d.ttf' % i, data) for i in range(3)])
mk('bomb.zip', [('bomb.ttf', b'\0' * (24 * 1024 * 1024))])
open(os.path.join(tmp, 'notzip.zip'), 'wb').write(b'PK\x03\x04garbage')
PY
mkdir -p "$TMP/zx"
python3 -S "$ZX" "$TMP/good.zip" "$TMP/zx" 128 536870912 > "$TMP/zx.log"
test "$(wc -l < "$TMP/zx.log" | tr -d ' ')" = 3 || fail "good.zip extracted: $(cat "$TMP/zx.log")"
test -s "$TMP/zx/Plain.ttf" && test -s "$TMP/zx/Plain-2.ttf" && test -s "$TMP/zx/Web.woff" || fail 'flattened names'
! ls -A "$TMP/zx" | grep -q -v -E '^(Plain\.ttf|Plain-2\.ttf|Web\.woff)$' || fail "unexpected files: $(ls -A "$TMP/zx")"
for case in slip abs ctrl link notzip; do
    d="$TMP/zx-$case"; mkdir -p "$d"
    rc=0; python3 -S "$ZX" "$TMP/$case.zip" "$d" 128 536870912 >/dev/null 2>"$d.err" || rc=$?
    test "$rc" -eq 1 || fail "$case.zip rc=$rc"
    test -z "$(ls -A "$d")" || fail "$case.zip wrote files"
    test ! -e "$TMP/evil.ttf" || fail 'path traversal escaped'
done
grep -q '符号链接' "$TMP/zx-link.err" || fail "link reason: $(cat "$TMP/zx-link.err")"
mkdir -p "$TMP/zx-many"
rc=0; python3 -S "$ZX" "$TMP/many.zip" "$TMP/zx-many" 2 536870912 >/dev/null 2>"$TMP/many.err" || rc=$?
test "$rc" -eq 1 && grep -q '字体数量超过上限' "$TMP/many.err" || fail 'file count limit'
mkdir -p "$TMP/zx-total"
rc=0; python3 -S "$ZX" "$TMP/many.zip" "$TMP/zx-total" 128 100000 >/dev/null 2>"$TMP/total.err" || rc=$?
test "$rc" -eq 1 && grep -q '总大小超过上限' "$TMP/total.err" || fail 'total size limit'
mkdir -p "$TMP/zx-bomb"
rc=0; python3 -S "$ZX" "$TMP/bomb.zip" "$TMP/zx-bomb" 128 536870912 >/dev/null 2>"$TMP/bomb.err" || rc=$?
test "$rc" -eq 1 && grep -q '解压炸弹' "$TMP/bomb.err" || fail "bomb: $(cat "$TMP/bomb.err")"
test -z "$(ls -A "$TMP/zx-bomb")" || fail 'bomb partial file left'

# ---- ZIP 导入：包内 WOFF 解包后入库；不安全的包整体拒绝 ------------------------------------
run_zip_import() {
    _root="$TMP/imp-$1"; mkdir -p "$_root/public/import" "$_root/public/fonts" "$_root/cache" "$_root/config"
    cp "$2" "$_root/public/import/$1.zip"
    sh -c '
        set -eu
        MODDIR="$1"; MODULE_DIR="$1"; CONFIG_DIR="$2/config"
        LUOSHU_PUBLIC_DIR="$2/public"; USER_FONTS_DIR="$2/public/fonts"
        USER_IMPORT_DIR="$2/public/import"; IMPORT_CACHE_DIR="$2/cache"
        json_escape() { printf "%s" "$1" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g" | tr "\n\r" "  "; }
        . "$1/common/util_functions.sh"
        . "$1/common/font_check.sh"
        . "$1/common/font_import.sh"
        . "$1/common/font_import_compat.sh"
        import_zip_package "$3.zip"
    ' sh "$ROOT" "$_root" "$1"
}
python3 - "$TMP/webonly.zip" "$TMP/src/Sample.woff" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('module.prop', 'id=web_only\nname=网页字体包\nversion=1\n')
    z.write(sys.argv[2], 'fonts/WebSans.woff')
PY
OUT=$(run_zip_import webonly "$TMP/webonly.zip")
printf '%s\n' "$OUT" | grep -q '"status":"ok"' || fail "web zip import: $OUT"
find "$TMP/imp-webonly/public/fonts" -type f -name '*.ttf' -print -quit | grep -q . || fail 'web zip produced no ttf'
! find "$TMP/imp-webonly/public/fonts" -type f -iname '*.woff*' -print -quit | grep -q . || fail 'woff copied as-is'

OUT=$(run_zip_import slip "$TMP/slip.zip")
printf '%s\n' "$OUT" | grep -q '"message":"字体包未通过安全检查：字体条目路径不安全' || fail "slip import: $OUT"

python3 - "$TMP/badweb.zip" "$TMP/src/Bad.woff" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(sys.argv[2], 'Bad.woff')
PY
OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 run_zip_import badweb "$TMP/badweb.zip")
printf '%s\n' "$OUT" | grep -q '"message":"检测到网页字体 WOFF，不能仅修改扩展名后作为系统字体"' || fail "bad web zip: $OUT"

# App 导入桥接入
grep -q 'woff|woff2) import_web_font' "$ROOT/common/native_import.sh" || fail 'native import not wired'
grep -q 'font_prepare_import' "$ROOT/common/native_import.sh" || fail 'native import not using prepare'

# ---- WOFF2 ---------------------------------------------------------------------
DEC="${LUOSHU_TEST_WOFF2_DECODER:-}"
if [ -z "$DEC" ] && [ "${LUOSHU_WOFF2_TEST_BUILD:-0}" = 1 ]; then
    sh "$ROOT/scripts/build_woff2_decoder.sh" "$TMP/luoshu-woff2-decode"
    DEC="$TMP/luoshu-woff2-decode"
fi
# 缺少解码器时给出明确原因
OUT=$(printf 'wOF2' | cat - "$TMP/src/Plain.ttf" > "$TMP/src/Fake.woff2"; \
      LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 LUOSHU_WOFF2_DECODER="$TMP/none" python3 -S "$CONV" "$TMP/src/Fake.woff2" "$TMP/out" || true)
printf '%s\n' "$OUT" | grep -q '缺少 WOFF2 解码组件' || fail "missing decoder: $OUT"

if [ -z "$DEC" ]; then
    echo 'Web font import test: WOFF2 decoder cases skipped (no decoder).'
    echo 'Web font import test passed.'
    exit 0
fi
# 生成 WOFF2 需要宿主 Brotli（python3-brotli）；不加 -S 以便使用系统包。
if ! python3 - "$TMP/src/Plain.ttf" "$TMP/src/Sample.woff2" <<'PY'
import sys
from fontTools.ttLib import TTFont
f = TTFont(sys.argv[1]); f.flavor = 'woff2'; f.save(sys.argv[2])
PY
then
    fail 'cannot create WOFF2 fixture (install python3-brotli)'
fi
OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 LUOSHU_WOFF2_DECODER="$DEC" python3 -S "$CONV" "$TMP/src/Sample.woff2" "$TMP/out")
printf '%s\n' "$OUT" | grep -q '"method":"woff2-decoder"' || fail "woff2 decode: $OUT"
python3 -S - "$TMP/src/Plain.ttf" "$TMP/out/Sample.ttf" <<'PY'
import sys
from fontTools.ttLib import TTFont
a, b = TTFont(sys.argv[1]), TTFont(sys.argv[2])
assert b.flavor is None
assert set(a.getBestCmap()) == set(b.getBestCmap())
assert a['maxp'].numGlyphs == b['maxp'].numGlyphs
PY
head -c 5000 "$TMP/src/Sample.woff2" > "$TMP/src/Broken.woff2"
OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 LUOSHU_WOFF2_DECODER="$DEC" python3 -S "$CONV" "$TMP/src/Broken.woff2" "$TMP/out" || true)
printf '%s\n' "$OUT" | grep -q 'WOFF2 解码失败' || fail "broken woff2: $OUT"

python3 - "$TMP/w2.zip" "$TMP/src/Sample.woff2" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_STORED) as z:
    z.write(sys.argv[2], 'Web2Sans.woff2')
PY
OUT=$(LUOSHU_WEB_CONVERT_NO_FONTTOOLS=1 LUOSHU_WOFF2_DECODER="$DEC" run_zip_import w2 "$TMP/w2.zip")
printf '%s\n' "$OUT" | grep -q '"status":"ok"' || fail "woff2 zip import: $OUT"
echo 'Web font import test passed (including WOFF2).'
