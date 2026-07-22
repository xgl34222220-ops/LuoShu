#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/version.sh"

# 所有 Shell 与 Python 后端必须先通过基础语法检查。
find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do
  sh -n "$file"
done
[ ! -f "$ROOT/common/play_font_bridge" ] || sh -n "$ROOT/common/play_font_bridge"
[ ! -f "$ROOT/common/wechat_xweb_bridge" ] || sh -n "$ROOT/common/wechat_xweb_bridge"
python3 -m py_compile \
  "$ROOT/common/composite_font.py" \
  "$ROOT/common/font_instance.py" \
  "$ROOT/common/font_coverage.py" \
  "$ROOT/common/font_axis_info.py" \
  "$ROOT/common/font_role_check.py" \
  "$ROOT/common/font_metadata.py" \
  "$ROOT/common/font_extract_faces.py" \
  "$ROOT/common/font_import_probe.py"

# App-only 活跃源码清单。WebUI 前端及其准备脚本必须彻底不存在。
for file in \
  module.prop customize.sh post-fs-data.sh service.sh uninstall.sh action.sh \
  README.md README.txt LICENSE NOTICE.md THIRD_PARTY_NOTICES.md CHANGELOG.md SECURITY.md CONTRIBUTING.md \
  common/composite_font.py common/font_instance.py common/font_coverage.py common/font_axis_info.py \
  common/font_role_check.py common/font_metadata.py common/font_extract_faces.py common/font_import_probe.py \
  common/font_role_check.sh common/native_import.sh common/font_details.sh common/luoshu_cli.sh \
  common/luoshu_composite.sh common/font_mix.sh common/v14_mix.sh common/v142_weighted_mix.sh \
  common/v143_auto_multiweight_mix.sh common/mix_weight_mode.sh \
  common/app_bridge.sh common/font_manager.sh common/font_library_cache.sh common/app_installer.sh \
  common/mount_compat.sh common/rom_adapters.sh common/hyperos_global.sh common/util_functions.sh \
  scripts/build.sh scripts/version.sh scripts/prepare_composite_runtime.sh scripts/mount_compat_test.sh \
  scripts/stability_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh \
  scripts/font_library_cache_test.sh scripts/app_installer_test.sh scripts/hyperos_global_mapping_test.sh \
  scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/rc3_audit.sh \
  docs/RELEASING.md docs/TEST_MATRIX.md \
  android-app/app/build.gradle.kts \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/MainActivity.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuHost.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportViewModel.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportQueueStore.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/FontMetadataInspector.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/font/FontDefaultAxes.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/appearance/AppearanceSettings.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/TaskCenterModel.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsContract.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsRoute.kt \
  android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/ImportTaskControls.kt \
  android-app/app/src/test/java/io/github/xgl34222220/luoshu/NativeImportStateTest.kt \
  android-app/app/src/test/java/io/github/xgl34222220/luoshu/NativeImportQueueStoreTest.kt \
  android-app/app/src/test/java/io/github/xgl34222220/luoshu/NativeImportTaskCenterTest.kt \
  android-app/app/src/test/java/io/github/xgl34222220/luoshu/NativeImportControlsTest.kt \
  android-app/app/src/test/java/io/github/xgl34222220/luoshu/ui/logs/TaskCenterModelTest.kt \
  android-app/app/src/test/java/io/github/xgl34222220/luoshu/ui/appearance/AppearanceSettingsTest.kt; do
  test -f "$ROOT/$file"
done
test ! -d "$ROOT/webroot"
test ! -e "$ROOT/scripts/prepare_webui.sh"
! grep -q '^webroot=' "$ROOT/module.prop"

# module.prop 是模块、原生 App 和产物的唯一版本源。
test "$LUOSHU_VERSION" = "$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n1)"
test "$LUOSHU_VERSION_CODE" = "$(sed -n 's/^versionCode=//p' "$ROOT/module.prop" | head -n1)"
test "$LUOSHU_VERSION" = "$(sed -n 's/^version=//p' "$ROOT/config/version_notes.conf" | head -n1)"
grep -q '^description=Android 无 Hook 全局字体引擎' "$ROOT/module.prop"

# 单包构建必须显式传入 APK；Debug 包只能由测试工作流明确放行。
grep -q "LUOSHU_APP_APK is required" "$ROOT/scripts/build.sh"
grep -q 'LUOSHU_ALLOW_DEBUG_APP' "$ROOT/scripts/build.sh"
grep -q 'io.github.xgl34222220.luoshu.debug' "$ROOT/scripts/build.sh"
grep -q 'LuoShu-${VERSION}.zip' "$ROOT/scripts/build.sh"
! grep -RIn 'LUOSHU_VARIANT' "$ROOT/scripts" "$ROOT/.github/workflows" >/dev/null 2>&1

# 安装与运行时只面向原生 App，不得重新创建或依赖 webroot。
grep -q 'luoshu_cli.sh.*system/bin/洛书' "$ROOT/customize.sh"
! grep -q 'pm install' "$ROOT/customize.sh"
! grep -q 'pkill' "$ROOT/customize.sh"
for runtime in customize.sh post-fs-data.sh service.sh action.sh common/font_manager.sh common/app_bridge.sh; do
  ! grep -q 'webroot' "$ROOT/$runtime"
done
grep -q 'native_font_index.json' "$ROOT/common/font_manager.sh"
grep -q 'native_font_index.json' "$ROOT/service.sh"
! grep -qE 'restart_ui|previous_font|sync_preview_fonts' "$ROOT/common/font_manager.sh"
! grep -qE '重启界面|刷新字体缓存|回滚' "$ROOT/common/luoshu_cli.sh"

# 字体处理、安全门禁和原生桥能力必须保留。
grep -q 'full-composite-v5' "$ROOT/common/font_mix.sh"
grep -q 'build_composite_file' "$ROOT/common/font_mix.sh"
grep -q 'v142_weighted_mix.sh' "$ROOT/common/v14_mix.sh"
grep -q 'v143_auto_multiweight_mix.sh' "$ROOT/common/v14_mix.sh"
grep -q 'infer_mix_weight_mode' "$ROOT/common/v14_mix.sh"
grep -q 'font_role_check.sh' "$ROOT/common/v14_mix.sh"
grep -q 'for _weight in 100 200 300 400 500 600 700 800 900' "$ROOT/common/v143_auto_multiweight_mix.sh"
grep -q 'build_composite_cached' "$ROOT/common/v143_auto_multiweight_mix.sh"
grep -q 'LuoShuAutoMix' "$ROOT/common/v143_auto_multiweight_mix.sh"
grep -q 'cjkMode=%s' "$ROOT/common/v143_auto_multiweight_mix.sh"
grep -q 'mix_variable_default_weight' "$ROOT/common/mix_weight_mode.sh"
grep -q 'common/v14_mix.sh' "$ROOT/common/app_bridge.sh"
grep -q 'native_import.sh' "$ROOT/common/app_bridge.sh"
grep -q 'preview_source)' "$ROOT/common/app_bridge.sh"
grep -q 'find_preview_source' "$ROOT/common/app_bridge.sh"
grep -q 'sha256' "$ROOT/common/app_bridge.sh"
grep -q 'rebootRequired' "$ROOT/common/app_bridge.sh"
grep -q 'trusted_source' "$ROOT/common/native_import.sh"
grep -q 'MAX_BYTES=268435456' "$ROOT/common/native_import.sh"
grep -q 'font_validate' "$ROOT/common/native_import.sh"
grep -q 'font_extract_faces.py' "$ROOT/common/native_import.sh"
grep -q 'font_check_cli' "$ROOT/common/font_check.sh"
grep -q 'source 时，必须只定义函数' "$ROOT/common/font_check.sh"
grep -q 'instantiateVariableFont' "$ROOT/common/font_instance.py"
grep -q -- '--axes' "$ROOT/common/font_instance.py"
grep -q 'worker "$_request"' "$ROOT/common/v142_weighted_mix.sh"
grep -q 'axes_task.conf' "$ROOT/common/v142_weighted_mix.sh"
grep -q 'OpenMultipleDocuments' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'takePersistableUriPermission' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportViewModel.kt"
grep -q 'fun pauseImport' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportViewModel.kt"
grep -q 'fun cancelImport' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportViewModel.kt"
grep -q 'fun retryFailed' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportViewModel.kt"
grep -q 'fun clearRecord' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportViewModel.kt"
grep -q 'forResume' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportQueueStore.kt"
grep -q 'forRetryFailures' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportQueueStore.kt"
grep -q 'cancelRemaining' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportQueueStore.kt"
grep -q 'encodeImportQueue' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportQueueStore.kt"
grep -q 'viewModel<NativeImportViewModel>()' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuHost.kt"
grep -q 'setFontVariationSettings' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
grep -q 'updateMixAxis' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'resolveAndCacheFontDefaultAxes' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/dialogs/FontPickerDialog.kt"
grep -q 'cachedFontDefaultWeight' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/font/FontUiSupport.kt"
grep -q 'optDouble("default"' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/font/FontDefaultAxes.kt"
grep -q 'testImplementation("junit:junit:4.13.2")' "$ROOT/android-app/app/build.gradle.kts"

# HyperOS 必须保留紧凑控件的原厂度量壳，并按真实分区写入 MiSans 与数字字重目标。
grep -q '_hyperos_metric_shell_files' "$ROOT/common/hyperos_global.sh"
grep -q 'LUOSHU_PRODUCT_FONTS_ROOT' "$ROOT/common/hyperos_global.sh"
grep -q 'font_instance.py' "$ROOT/common/hyperos_global.sh"
grep -q 'hyperos_global.sh' "$ROOT/common/font_library_cache.sh"
grep -q 'hyperos_global.sh' "$ROOT/common/mount_compat.sh"
! grep -q '_font_alias.*Roboto' "$ROOT/common/hyperos_global.sh"

# 禁止重新引入高风险热刷新；字体 XML 只能由运行时事务层生成，不能作为静态系统负载提交。
! grep -q 'cmd font system --update' "$ROOT/service.sh"
! grep -q 'oplus-font refresh' "$ROOT/service.sh"
! find "$ROOT/system/etc" -type f \( -name fonts.xml -o -name font_fallback.xml \) -print -quit 2>/dev/null | grep -q .
! grep -RIn 'v143_axes' "$ROOT/common" "$ROOT/android-app" >/dev/null 2>&1

# 许可证与声明保持完整。
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

# 功能回归脚本。
sh "$ROOT/scripts/native_preview_source_test.sh"
sh "$ROOT/scripts/native_zip_import_test.sh"
sh "$ROOT/scripts/font_index_delete_regression_test.sh"
sh "$ROOT/scripts/rc3_audit.sh"
sh "$ROOT/scripts/mount_compat_test.sh"
sh "$ROOT/scripts/hyperos_global_mapping_test.sh"
sh "$ROOT/scripts/auto_multiweight_mode_test.sh"
sh "$ROOT/scripts/auto_multiweight_engine_test.sh"
sh "$ROOT/scripts/background_mix_worker_test.sh"
sh "$ROOT/scripts/mix_finalize_performance_test.sh"
sh "$ROOT/scripts/stability_test.sh"
sh "$ROOT/scripts/font_library_cache_test.sh"
sh "$ROOT/scripts/app_installer_test.sh"

test -x "$ROOT/common/python/bin/luoshu-python"
echo 'LuoShu App-only source checks passed.'

# Font refresh/import/mix performance contracts.
grep -q 'native-v3' common/font_manager.sh
grep -q 'manifest-fast' common/font_manager.sh
grep -q 'font-index-v3.json' android-app/app/src/main/java/io/github/xgl34222220/luoshu/FontIndexStore.kt
grep -q 'prepared-v2' common/v143_auto_multiweight_mix.sh
