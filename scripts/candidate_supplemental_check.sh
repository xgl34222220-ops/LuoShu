#!/bin/bash
# Supplemental gates are mandatory; preserve the failing check's exit status.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

sh -x scripts/background_task_test.sh
sh -x scripts/device_font_foreground_quick_test.sh
sh -x scripts/font_switch_task_test.sh
sh -x scripts/mount_fast_sync_test.sh
FONT="$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit)"
test -s "$FONT"
python3 scripts/font_inventory_scan_test.py --font "$FONT"
STOCK_CJK="$(find /usr/share/fonts -type f -iname 'NotoSansCJK-Regular.ttc' -print -quit)"
test -s "$STOCK_CJK"
PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}" \
  python3 scripts/composite_collection_real_test.py --stock "$STOCK_CJK"
grep -q '多字重 · ${weights.size} 档' android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/font/FontUiSupport.kt
grep -q '静态字体现在始终按当前所选字重走快速单文件组合' common/mix_weight_mode.sh
