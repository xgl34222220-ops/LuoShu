#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do sh -n "$file"; done
sh -n "$ROOT/common/play_font_bridge"
sh -n "$ROOT/common/wechat_xweb_bridge"
python3 -m py_compile "$ROOT/common/composite_font.py"

if command -v node >/dev/null 2>&1; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT HUP INT TERM
  for file in app.js font_analyzer.js kernelsu.js stability.js environment.js v14.js; do
    cp "$ROOT/webroot/$file" "$TMP/${file%.js}.mjs"
    node --check "$TMP/${file%.js}.mjs"
  done
  rm -rf "$TMP"; trap - EXIT HUP INT TERM
fi

for file in module.prop customize.sh post-fs-data.sh service.sh uninstall.sh \
  common/composite_font.py common/luoshu_composite.sh common/font_mix.sh common/v14_mix.sh \
  common/mount_compat.sh common/font_manager.sh webroot/index.html webroot/v14.js \
  scripts/build.sh scripts/prepare_composite_runtime.sh; do test -f "$ROOT/$file"; done

grep -q '^version=v14.1$' "$ROOT/module.prop"
grep -q '^versionCode=14120$' "$ROOT/module.prop"
grep -q '完整中英数字体复合' "$ROOT/module.prop"
grep -q 'full-composite-v5' "$ROOT/common/font_mix.sh"
grep -q 'build_composite_anchor' "$ROOT/common/font_mix.sh"
grep -q 'font_mix.sh.*recover' "$ROOT/post-fs-data.sh"
! grep -q 'cmd font system --update' "$ROOT/service.sh"
! grep -q 'oplus-font refresh' "$ROOT/service.sh"
! find "$ROOT/system/etc" -type f \( -name fonts.xml -o -name font_fallback.xml \) -print -quit 2>/dev/null | grep -q .
grep -q 'v14.js?v=14120' "$ROOT/webroot/index.html"
grep -q 'app.js?v=14120' "$ROOT/webroot/index.html"
grep -q "UI_VERSION = '14120'" "$ROOT/webroot/environment.js"

test -x "$ROOT/common/python/bin/luoshu-python"
test -f "$ROOT/common/python/lib/libpython3.14.so"
test -f "$ROOT/common/python/lib/python3.14/site-packages/fontTools/ttLib/__init__.py"
file "$ROOT/common/python/bin/luoshu-python" | grep -q 'ARM aarch64'

PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" \
  python3 -S - <<'PY'
from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.boundsPen import BoundsPen
print('Bundled FontTools import OK')
PY

echo 'LuoShu v14.1 source checks passed.'
