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
  for file in app.js font_analyzer.js kernelsu.js environment.js v14.js; do
    cp "$ROOT/webroot/$file" "$TMP/${file%.js}.mjs"
    node --check "$TMP/${file%.js}.mjs"
  done
  rm -rf "$TMP"; trap - EXIT HUP INT TERM
fi

for file in module.prop customize.sh post-fs-data.sh service.sh uninstall.sh \
  README.md README.txt LICENSE NOTICE.md THIRD_PARTY_NOTICES.md CHANGELOG.md SECURITY.md CONTRIBUTING.md \
  licenses/LuoShu-MIT-HISTORICAL.txt licenses/CPython-LICENSE.txt licenses/FontTools-LICENSE.txt licenses/FontTools-LICENSE.external.txt \
  common/composite_font.py common/luoshu_composite.sh common/font_mix.sh common/v14_mix.sh \
  common/mount_compat.sh common/font_manager.sh webroot/index.html webroot/v14.js \
  scripts/build.sh scripts/prepare_composite_runtime.sh; do test -f "$ROOT/$file"; done

grep -q '^version=v14.1.1 RC3$' "$ROOT/module.prop"
grep -q '^versionCode=14123$' "$ROOT/module.prop"
grep -q '^description=Android 全局文字字体复合模块' "$ROOT/module.prop"
grep -q 'full-composite-v5' "$ROOT/common/font_mix.sh"
grep -q 'build_composite_file' "$ROOT/common/font_mix.sh"
grep -q 'font_mix.sh.*recover' "$ROOT/post-fs-data.sh"
! grep -q 'cmd font system --update' "$ROOT/service.sh"
! grep -q 'oplus-font refresh' "$ROOT/service.sh"
! find "$ROOT/system/etc" -type f \( -name fonts.xml -o -name font_fallback.xml \) -print -quit 2>/dev/null | grep -q .
grep -q 'v14.js?v=14120' "$ROOT/webroot/index.html"
grep -q 'app.js?v=14120' "$ROOT/webroot/index.html"
grep -q "UI_VERSION = '14120'" "$ROOT/webroot/environment.js"

test "$(sha256sum "$ROOT/LICENSE" | awk '{print $1}')" = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
grep -q 'GNU GENERAL PUBLIC LICENSE' "$ROOT/LICENSE"
grep -q 'Version 3, 29 June 2007' "$ROOT/LICENSE"
grep -q 'END OF TERMS AND CONDITIONS' "$ROOT/LICENSE"
grep -q 'GPL-3.0-only' "$ROOT/README.md"
grep -q 'GPL-3.0-only' "$ROOT/README.txt"
grep -q 'GPL-3.0-only' "$ROOT/NOTICE.md"
grep -q 'GPL-3.0-only' "$ROOT/THIRD_PARTY_NOTICES.md"
grep -q 'GPL-3.0-only' "$ROOT/CONTRIBUTING.md"
! grep -q 'License-MIT' "$ROOT/README.md"
grep -q '^MIT License$' "$ROOT/licenses/LuoShu-MIT-HISTORICAL.txt"
grep -q 'Python Software Foundation' "$ROOT/licenses/CPython-LICENSE.txt"
grep -q '^MIT License$' "$ROOT/licenses/FontTools-LICENSE.txt"
if cmp -s "$ROOT/licenses/CPython-LICENSE.txt" "$ROOT/licenses/FontTools-LICENSE.txt"; then
  echo 'CPython and FontTools license files must not be identical.' >&2
  exit 1
fi
! grep -q '/sdcard/LuoShu/emoji/' "$ROOT/README.md" "$ROOT/README.txt" "$ROOT/module.prop" "$ROOT/config/version_notes.conf"

sh "$ROOT/scripts/rc3_audit.sh"

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

echo 'LuoShu v14.1.1 RC3 clean-baseline checks passed.'
