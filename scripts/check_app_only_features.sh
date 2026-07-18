#!/bin/sh
set -eu

ROOT="${1:-$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)}"
cd "$ROOT"

sh -n common/app_bridge.sh
sh -n common/app_multiweight_mix.sh
sh -n common/font_manager.sh
sh -n common/rom_adapters.sh

grep -q 'OpenMultipleDocuments' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt
grep -q 'APP 专属导入' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt
grep -q '默认多字重' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt
grep -q 'cjkAuto' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
grep -q 'stageFontImports' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
grep -q 'app_multiweight_mix.sh' common/app_bridge.sh
grep -q '/cache/font-import/' common/app_bridge.sh
grep -q 'LUOSHU_PRIVATE_LIBRARY' common/font_manager.sh

# App-only contract: none of the new UI labels or commands may appear in WebUI sources.
if grep -R -n -E 'APP 专属导入|默认多字重|app_multiweight_mix|font-import' webroot 2>/dev/null; then
    echo 'App-only font features leaked into WebUI sources' >&2
    exit 1
fi

printf 'ok\n'
