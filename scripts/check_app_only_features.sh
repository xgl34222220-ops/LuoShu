#!/bin/sh
set -eu

ROOT="${1:-$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)}"
cd "$ROOT"

for file in \
  common/app_bridge.sh \
  common/app_font_import.sh \
  common/app_multiweight_mix.sh \
  common/app_multiweight_real.sh \
  common/font_check.sh \
  common/font_metadata_runtime.sh \
  common/font_manager.sh \
  common/rom_adapters.sh; do
  sh -n "$file"
done

python3 -m py_compile \
  common/font_metadata.py \
  common/font_package_import.py \
  common/font_family_rewrite.py \
  common/font_instance.py

grep -q 'OpenMultipleDocuments' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt
grep -q 'application/zip' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt
grep -q '扫描模块' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt
grep -q 'supportedImportExtensions = setOf("ttf", "otf", "ttc", "zip")' android-app/app/src/main/java/io/github/xgl34222220/luoshu/AppFontImport.kt
grep -q 'importInstalledFontModules' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
grep -q 'import_package' common/app_bridge.sh
grep -q 'import_modules' common/app_bridge.sh
grep -q 'font_metadata_runtime.sh' common/font_check.sh
grep -q 'font_family_for_file' common/font_metadata_runtime.sh
grep -q 'family_weight_numbers' common/app_multiweight_real.sh
grep -q 'font_file_is_variable' common/app_multiweight_real.sh
grep -q 'detect_font_family "$(basename' common/font_manager.sh
grep -q 'modulePackage' common/font_package_import.py
grep -q 'MAX_FONT_FILES = 300' common/font_package_import.py
grep -q '/data/adb/modules' common/app_font_import.sh
grep -q '/data/adb/modules_update' common/app_font_import.sh
grep -q 'LUOSHU_PRIVATE_LIBRARY' common/font_manager.sh

if grep -q 'AUTO_SET=' common/app_multiweight_real.sh; then
  echo 'Fixed five-weight mapping returned to the App engine' >&2
  exit 1
fi

# App-only contract: none of the new UI labels or commands may appear in WebUI sources.
if grep -R -n -E 'APP 专属导入|扫描模块|默认多字重|app_multiweight_real|import_modules|font-import' webroot 2>/dev/null; then
  echo 'App-only font features leaked into WebUI sources' >&2
  exit 1
fi

printf 'ok\n'
