#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
CHECK = ROOT / "scripts/check.sh"

shell = SHELL.read_text(encoding="utf-8")
marker = "private fun MiuixAppDock("
if marker not in shell:
    raise SystemExit("MiuixAppDock not found")
head, tail = shell.split(marker, 1)
old_icon = "modifier = Modifier.size(if (selected) 22.dp else 20.dp),"
new_icon = "modifier = Modifier.size(if (selected) 21.dp else 19.dp),"
if new_icon not in tail:
    if tail.count(old_icon) != 1:
        raise SystemExit(f"MiuixAppDock icon match count: {tail.count(old_icon)}")
    tail = tail.replace(old_icon, new_icon, 1)
SHELL.write_text(head + marker + tail, encoding="utf-8")

test_script = '''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
OVERLAY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"

grep -q 'private fun MiuixCapabilityStrip' "$MIUIX"
grep -q 'label = "查看详情"' "$MIUIX"
grep -q 'label = "应用字体"' "$MIUIX"
grep -q 'topActions()' "$MIUIX"
grep -q 'topActions()' "$MATERIAL"
grep -q 'topActions: @Composable' "$ROUTE"
grep -q 'embedded: Boolean = false' "$OVERLAY"
grep -q 'embedded = true' "$SHELL"
grep -q 'libraryDockClearance' "$SHELL"
grep -q 'if (page == AppPage.Studio)' "$SHELL"
! grep -q 'page == AppPage.Library || page == AppPage.Studio' "$SHELL"

CARD=$(sed -n '/private fun MiuixFontCard/,/private fun MiuixLibraryNotice/p' "$MIUIX")
printf '%s\n' "$CARD" | grep -q 'Arrangement.spacedBy(10.dp)'
printf '%s\n' "$CARD" | grep -q 'Modifier.weight(1f)'
printf '%s\n' "$CARD" | grep -q 'softWrap = false'
printf '%s\n' "$CARD" | grep -q 'MiuixCapabilityStrip(fontCapabilityLabel(font))'
! printf '%s\n' "$CARD" | grep -q 'Spacer(Modifier.weight(1f))'

DOCK=$(sed -n '/private fun MiuixAppDock/,/$p' "$SHELL")
printf '%s\n' "$DOCK" | grep -q 'height(54.dp)'
printf '%s\n' "$DOCK" | grep -q 'size(if (selected) 21.dp else 19.dp)'

echo 'Font library UI layout regression passed.'
'''
test_path = ROOT / "scripts/font_library_ui_layout_test.sh"
test_path.write_text(test_script, encoding="utf-8")
test_path.chmod(0o755)

check = CHECK.read_text(encoding="utf-8")
old_inventory = "scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/rc3_audit.sh"
new_inventory = "scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/font_library_ui_layout_test.sh scripts/rc3_audit.sh"
if new_inventory not in check:
    if check.count(old_inventory) != 1:
        raise SystemExit(f"check inventory match count: {check.count(old_inventory)}")
    check = check.replace(old_inventory, new_inventory, 1)
old_run = 'sh "$ROOT/scripts/mix_finalize_performance_test.sh"\nsh "$ROOT/scripts/stability_test.sh"'
new_run = 'sh "$ROOT/scripts/mix_finalize_performance_test.sh"\nsh "$ROOT/scripts/font_library_ui_layout_test.sh"\nsh "$ROOT/scripts/stability_test.sh"'
if new_run not in check:
    if check.count(old_run) != 1:
        raise SystemExit(f"check run match count: {check.count(old_run)}")
    check = check.replace(old_run, new_run, 1)
CHECK.write_text(check, encoding="utf-8")

(ROOT / ".ui-cleanup-retry").unlink(missing_ok=True)
(ROOT / "scripts/ui_cleanup_failure.log").unlink(missing_ok=True)
Path(__file__).unlink()
print("Font library UI cleanup completed.")
