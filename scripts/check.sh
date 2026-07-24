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
  "$ROOT/common/font_metrics_normalize.py" \
  "$ROOT/common/font_coverage.py" \
  "$ROOT/common/font_axis_info.py" \
  "$ROOT/common/font_role_check.py" \
  "$ROOT/common/font_metadata.py" \
  "$ROOT/common/font_extract_faces.py" \
  "$ROOT/common/font_import_probe.py" \
  "$ROOT/common/font_inventory.py"

# App-only 活跃源码清单。WebUI 前端及其准备脚本必须彻底不存在。
for file in \
  module.prop customize.sh post-fs-data.sh service.sh uninstall.sh action.sh \
  README.md README.txt LICENSE NOTICE.md THIRD_PARTY_NOTICES.md CHANGELOG.md SECURITY.md CONTRIBUTING.md \
  common/composite_font.py common/font_instance.py common/font_metrics_normalize.py common/font_coverage.py common/font_axis_info.py \
  common/font_role_check.py common/font_metadata.py common/font_extract_faces.py common/font_import_probe.py common/font_inventory.py \
  common/font_role_check.sh common/native_import.sh common/font_details.sh common/luoshu_cli.sh \
  common/luoshu_composite.sh common/font_mix.sh common/font_mix_controller.sh common/weighted_mix_task.sh \
  common/multiweight_mix_task.sh common/mix_weight_mode.sh \
  common/app_bridge.sh common/font_manager.sh common/font_library_cache.sh common/app_installer.sh \
  common/font_provider_cache.sh \
  common/mount_compat.sh common/rom_adapters.sh common/hyperos_global.sh common/util_functions.sh \
  scripts/build.sh scripts/version.sh scripts/module_payload_manifest.txt scripts/prepare_composite_runtime.sh scripts/mount_compat_test.sh scripts/customize_reenable_test.sh \
  scripts/stability_test.sh scripts/native_zip_import_test.sh scripts/native_preview_source_test.sh \
  scripts/font_library_cache_test.sh scripts/app_installer_test.sh scripts/hyperos_global_mapping_test.sh scripts/coloros_consistency_mapping_test.sh scripts/font_config_variable_weight_test.sh scripts/font_metrics_normalization_test.py scripts/font_config_monospace_test.py \
  scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/font_library_ui_layout_test.sh scripts/v2_source_audit.sh \
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

# 发布包使用显式清单。common/ 新增运行文件必须被审查后列入，不能再整目录复制。
PAYLOAD_MANIFEST="$ROOT/scripts/module_payload_manifest.txt"
test -s "$PAYLOAD_MANIFEST"
awk 'NF && $1 !~ /^#/ { if (seen[$0]++) exit 1 }' "$PAYLOAD_MANIFEST"
while IFS= read -r payload || [ -n "$payload" ]; do
  case "$payload" in ''|\#*) continue ;; esac
  test -e "$ROOT/$payload"
done < "$PAYLOAD_MANIFEST"
find "$ROOT/common" -maxdepth 1 -type f -printf 'common/%f\n' | sort > /tmp/luoshu-common-files.txt
grep '^common/' "$PAYLOAD_MANIFEST" | grep -v '^common/python$' | sort > /tmp/luoshu-manifest-common.txt
cmp -s /tmp/luoshu-common-files.txt /tmp/luoshu-manifest-common.txt

# 活跃运行时代码不得再出现历史开发版本头、WebUI 函数或未使用的报告脚本。
! grep -RInE --exclude-dir=python '(^|[^0-9])v1[34](\.|[^0-9])|Beta[[:space:]]*[0-9]|Hotfix' \
  "$ROOT/common" "$ROOT/customize.sh" "$ROOT/post-fs-data.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" >/dev/null 2>&1
! grep -qE 'get_all_fonts_json|get_font_info_json|scan_installed_families|refresh_font_cache' "$ROOT/common/util_functions.sh"
test ! -e "$ROOT/common/font_report.sh"
! grep -RInE 'webui_font_list|WebUI' "$ROOT/common" --exclude=module_update_state.sh >/dev/null 2>&1

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
grep -q 'full-composite-v11' "$ROOT/common/font_mix.sh"
grep -q 'build_composite_file' "$ROOT/common/font_mix.sh"
grep -q 'weighted_mix_task.sh' "$ROOT/common/font_mix_controller.sh"
grep -q 'multiweight_mix_task.sh' "$ROOT/common/font_mix_controller.sh"
grep -q 'infer_mix_weight_mode' "$ROOT/common/font_mix_controller.sh"
grep -q 'font_role_check.sh' "$ROOT/common/font_mix_controller.sh"
grep -q 'for _weight in 100 200 300 400 500 600 700 800 900' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'build_composite_cached' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'LuoShuAutoMix' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'cjkMode=%s' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'mix_variable_default_weight' "$ROOT/common/mix_weight_mode.sh"
grep -q 'common/font_mix_controller.sh' "$ROOT/common/app_bridge.sh"
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
grep -q 'normalize_font_metrics' "$ROOT/common/font_instance.py"
grep -q 'LuoShuMono' "$ROOT/common/font_config_overlay.py"
grep -q 'worker "$_request"' "$ROOT/common/weighted_mix_task.sh"
grep -q 'axes_task.conf' "$ROOT/common/weighted_mix_task.sh"
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


# v2 source namespace: old runtime filenames and obsolete bind-mount bridges must not return.
for obsolete in \
  common/v14_mix.sh common/v142_weighted_mix.sh common/v143_auto_multiweight_mix.sh common/v14_switch.sh \
  common/play_font_bridge common/wechat_xweb_bridge common/volume_key.sh common/legacy_data_fonts_cleanup.sh; do
  test ! -e "$ROOT/$obsolete"
done
for active in \
  common/font_mix_controller.sh common/weighted_mix_task.sh common/multiweight_mix_task.sh common/font_switch_task.sh \
  scripts/v2_source_audit.sh; do
  test -f "$ROOT/$active"
done
! grep -RInE --exclude-dir=.git --exclude=check.sh --exclude=CHANGELOG.md --exclude='RELEASE_NOTES_*' \
  'common/(v14_mix|v142_weighted_mix|v143_auto_multiweight_mix|v14_switch)\.sh' "$ROOT" >/dev/null 2>&1
! grep -RInE --exclude-dir=python '洛书 v1[34]\.|LuoShu v1[34]\.' \
  "$ROOT/common" "$ROOT/customize.sh" "$ROOT/post-fs-data.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" >/dev/null 2>&1

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
sh "$ROOT/scripts/v2_source_audit.sh"
sh "$ROOT/scripts/customize_reenable_test.sh"
sh "$ROOT/scripts/mount_compat_test.sh"
sh "$ROOT/scripts/hyperos_global_mapping_test.sh"
sh "$ROOT/scripts/coloros_consistency_mapping_test.sh"
FONT_INVENTORY_TEST_FONT=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
[ -s "$FONT_INVENTORY_TEST_FONT" ]
python3 "$ROOT/scripts/font_inventory_test.py" --font "$FONT_INVENTORY_TEST_FONT"
sh "$ROOT/scripts/rom_adapter_inventory_test.sh" "$FONT_INVENTORY_TEST_FONT"
sh "$ROOT/scripts/font_config_variable_weight_test.sh"
python3 "$ROOT/scripts/font_metrics_normalization_test.py"
python3 "$ROOT/scripts/font_config_monospace_test.py"
sh "$ROOT/scripts/auto_multiweight_mode_test.sh"
sh "$ROOT/scripts/auto_multiweight_engine_test.sh"
sh "$ROOT/scripts/background_mix_worker_test.sh"
sh "$ROOT/scripts/mix_finalize_performance_test.sh"
sh "$ROOT/scripts/font_switch_performance_test.sh"
sh "$ROOT/scripts/font_library_ui_layout_test.sh"
sh "$ROOT/scripts/stability_test.sh"
sh "$ROOT/scripts/font_library_cache_test.sh"
sh "$ROOT/scripts/app_installer_test.sh"

test -x "$ROOT/common/python/bin/luoshu-python"
echo 'LuoShu App-only source checks passed.'

# Font refresh/import/mix performance contracts.
grep -q 'native-v3' common/font_manager.sh
grep -q 'manifest-fast' common/font_manager.sh
grep -q 'font-index-v3.json' android-app/app/src/main/java/io/github/xgl34222220/luoshu/FontIndexStore.kt
grep -q 'prepared-v8' common/multiweight_mix_task.sh
