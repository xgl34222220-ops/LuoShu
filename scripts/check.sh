#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/version.sh"

find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do sh -n "$file"; done
sh -n "$ROOT/common/play_font_bridge"
sh -n "$ROOT/common/wechat_xweb_bridge"
python3 -m py_compile \
  "$ROOT/common/composite_font.py" \
  "$ROOT/common/font_instance.py" \
  "$ROOT/common/font_coverage.py" \
  "$ROOT/common/font_axis_info.py" \
  "$ROOT/common/font_role_check.py" \
  "$ROOT/common/font_metadata.py" \
  "$ROOT/common/font_extract_faces.py" \
  "$ROOT/common/font_import_probe.py"

if command -v node >/dev/null 2>&1; then
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT HUP INT TERM
  for file in app.js font_analyzer.js kernelsu.js environment.js v14.js workbench.js mix_state_guard.js workbench_bridge.js workbench_weight_extension.js; do
    cp "$ROOT/webroot/$file" "$TMP/${file%.js}.mjs"
    node --check "$TMP/${file%.js}.mjs"
  done
  rm -rf "$TMP"; trap - EXIT HUP INT TERM
fi

for file in module.prop customize.sh post-fs-data.sh service.sh uninstall.sh \
  README.md README.txt LICENSE NOTICE.md THIRD_PARTY_NOTICES.md CHANGELOG.md SECURITY.md CONTRIBUTING.md action.sh \
  RELEASE_NOTES_v14.2_ALPHA1.md RELEASE_NOTES_v14.2_ALPHA2.md RELEASE_NOTES_v14.2_ALPHA3.md \
  RELEASE_NOTES_v14.2_HYBRID_ALPHA5.md RELEASE_NOTES_v14.2_ALPHA6.md RELEASE_NOTES_v14.2_RC1.md RELEASE_NOTES_v14.2_RC2.md \
  RELEASE_NOTES_v14.3_ALPHA1.md \
  licenses/LuoShu-MIT-HISTORICAL.txt licenses/CPython-LICENSE.txt licenses/FontTools-LICENSE.txt licenses/FontTools-LICENSE.external.txt \
  common/composite_font.py common/font_instance.py common/font_coverage.py common/font_axis_info.py common/font_role_check.py common/font_metadata.py common/font_extract_faces.py common/font_import_probe.py \
  common/font_role_check.sh common/native_import.sh common/font_details.sh common/luoshu_cli.sh common/luoshu_composite.sh common/font_mix.sh common/v14_mix.sh \
  common/v142_weighted_mix.sh common/app_bridge.sh common/mount_compat.sh common/font_manager.sh webroot/index.html webroot/v14.js \
  webroot/workbench.js webroot/mix_state_guard.js webroot/workbench_bridge.js webroot/workbench.css \
  webroot/workbench_weight_extension.js webroot/workbench_weight_extension.css \
  scripts/build.sh scripts/version.sh scripts/prepare_webui.sh scripts/prepare_composite_runtime.sh scripts/mount_compat_test.sh scripts/stability_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh \
  docs/RELEASING.md docs/TEST_MATRIX.md \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/MainActivity.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuHost.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt; do test -f "$ROOT/$file"; done

test "$LUOSHU_VERSION" = "$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n1)"
test "$LUOSHU_VERSION_CODE" = "$(sed -n 's/^versionCode=//p' "$ROOT/module.prop" | head -n1)"
test "$LUOSHU_VERSION" = "$(sed -n 's/^version=//p' "$ROOT/config/version_notes.conf" | head -n1)"
grep -q '^description=Android 全局字体管理模块' "$ROOT/module.prop"
grep -q 'MODULE_VERSION=.*module.prop' "$ROOT/customize.sh"
grep -q 'luoshu_cli.sh.*system/bin/洛书' "$ROOT/customize.sh"
! grep -q 'pm install' "$ROOT/customize.sh"
! grep -q 'pkill' "$ROOT/customize.sh"
grep -q 'full-composite-v5' "$ROOT/common/font_mix.sh"
grep -q 'build_composite_file' "$ROOT/common/font_mix.sh"
grep -q 'v142_weighted_mix.sh' "$ROOT/common/v14_mix.sh"
grep -q 'font_role_check.sh' "$ROOT/common/v14_mix.sh"
grep -q 'common/v14_mix.sh' "$ROOT/common/app_bridge.sh"
grep -q 'native_import.sh' "$ROOT/common/app_bridge.sh"
grep -q 'import_file)' "$ROOT/common/app_bridge.sh"
grep -q 'preview_source)' "$ROOT/common/app_bridge.sh"
grep -q 'find_preview_source' "$ROOT/common/app_bridge.sh"
grep -q 'regular|normal' "$ROOT/common/app_bridge.sh"
grep -q 'sha256' "$ROOT/common/app_bridge.sh"
grep -q '预览失败' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
grep -q 'setFontVariationSettings' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
grep -q 'updateMixAxis' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'axisInfo.axes.forEach' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt"
! grep -q 'getOrNull()' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
grep -q 'trusted_source' "$ROOT/common/native_import.sh"
grep -q 'MAX_BYTES=268435456' "$ROOT/common/native_import.sh"
grep -q 'font_validate' "$ROOT/common/native_import.sh"
grep -q 'font_extract_faces.py' "$ROOT/common/native_import.sh"
grep -q 'native-import-zip-error' "$ROOT/common/native_import.sh"
grep -q 'font_check_cli' "$ROOT/common/font_check.sh"
grep -q 'source 时，必须只定义函数' "$ROOT/common/font_check.sh"
grep -q 'sourceUid' "$ROOT/common/font_extract_faces.py"
grep -q 'TTCFace' "$ROOT/common/font_extract_faces.py"
grep -q 'sha256:' "$ROOT/common/font_metadata.py"
grep -q 'usWeightClass' "$ROOT/common/font_import_probe.py"
grep -q 'import_probe_metadata' "$ROOT/common/font_import.sh"
grep -q 'extralight) num=200' "$ROOT/common/rom_adapters.sh"
grep -q 'extrabold) num=800' "$ROOT/common/rom_adapters.sh"
grep -q 'faceIndex' "$ROOT/common/font_metadata.py"
grep -q 'TTCollection' "$ROOT/common/font_metadata.py"
grep -q 'font_metadata.py' "$ROOT/common/font_details.sh"
grep -q 'OpenMultipleDocuments' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'native_import' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'font_details.sh' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q '稳定文件 ID' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'LuoShuHost' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/MainActivity.kt"
grep -q 'instantiateVariableFont' "$ROOT/common/font_instance.py"
grep -q -- '--axes' "$ROOT/common/font_instance.py"
grep -q 'worker "$_request"' "$ROOT/common/v142_weighted_mix.sh"
grep -q 'cjkAxes' "$ROOT/common/v142_weighted_mix.sh"
grep -q 'axes_task.conf' "$ROOT/common/v142_weighted_mix.sh"
grep -q 'rebootRequired' "$ROOT/common/app_bridge.sh"
grep -q 'taskId' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'coerceIn(1, 1000)' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'restartUIBtn' "$ROOT/webroot/environment.js"
grep -q 'restartUi.hidden = true' "$ROOT/webroot/environment.js"
grep -q 'v14_mix.sh.*recover' "$ROOT/post-fs-data.sh"
! grep -RIn 'v143_axes' "$ROOT/common" "$ROOT/android-app" "$ROOT/webroot" >/dev/null 2>&1
! grep -qE '回滚|重启界面|刷新字体缓存' "$ROOT/common/luoshu_cli.sh"
! grep -q 'cmd font system --update' "$ROOT/service.sh"
! grep -q 'oplus-font refresh' "$ROOT/service.sh"
! find "$ROOT/system/etc" -type f \( -name fonts.xml -o -name font_fallback.xml \) -print -quit 2>/dev/null | grep -q .
grep -q 'MODULE_VERSION=.*module.prop' "$ROOT/service.sh"
grep -q 'MODULE_VERSION=.*module.prop' "$ROOT/post-fs-data.sh"
! grep -q 'v14.2 Alpha2' "$ROOT/service.sh" "$ROOT/post-fs-data.sh"
grep -q 'workbench_weight_extension.js' "$ROOT/webroot/workbench_bridge.js"
grep -q 'mix-axis-panel' "$ROOT/webroot/workbench_weight_extension.css"
grep -q 'serializeAxes' "$ROOT/webroot/workbench_weight_extension.js"

# 源码中的缓存键允许保持上个版本；构建前必须能由唯一版本源正确重写。
WEB_TMP=$(mktemp -d)
trap 'rm -rf "$WEB_TMP"' EXIT HUP INT TERM
cp "$ROOT/module.prop" "$WEB_TMP/module.prop"
cp -R "$ROOT/webroot" "$WEB_TMP/webroot"
sh "$ROOT/scripts/prepare_webui.sh" "$WEB_TMP/webroot"
grep -q "v14.js?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/index.html"
grep -q "app.js?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/index.html"
grep -q "UI_VERSION = '$LUOSHU_VERSION_CODE'" "$WEB_TMP/webroot/environment.js"
grep -q "mix_state_guard.js?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/environment.js"
grep -q "workbench_bridge.js?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/environment.js"
grep -q "workbench.js?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/environment.js"
grep -q "workbench.css?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/workbench.js"
grep -q "workbench_weight_extension.css?v=$LUOSHU_VERSION_CODE" "$WEB_TMP/webroot/workbench_weight_extension.js"
rm -rf "$WEB_TMP"; trap - EXIT HUP INT TERM

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

sh "$ROOT/scripts/native_preview_source_test.sh"
sh "$ROOT/scripts/native_zip_import_test.sh"
sh "$ROOT/scripts/rc3_audit.sh"
sh "$ROOT/scripts/mount_compat_test.sh"
sh "$ROOT/scripts/stability_test.sh"

test -x "$ROOT/common/python/bin/luoshu-python"
test -f "$ROOT/common/python/lib/libpython3.14.so"
test -f "$ROOT/common/python/lib/python3.14/site-packages/fontTools/ttLib/__init__.py"
test -f "$ROOT/common/python/lib/python3.14/site-packages/fontTools/varLib/instancer/__init__.py"
file "$ROOT/common/python/bin/luoshu-python" | grep -q 'ARM aarch64'

PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" \
  python3 -S - <<'PY'
from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.instancer import instantiateVariableFont
print('Bundled FontTools import OK')
PY

echo "LuoShu $LUOSHU_VERSION hybrid checks passed."
