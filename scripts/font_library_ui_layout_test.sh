#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
OVERLAY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"

grep -q 'private fun MiuixCapabilityStrip' "$MIUIX"
grep -q 'private fun MaterialCapabilityStrip' "$MATERIAL"
grep -q 'label = "查看详情"' "$MIUIX"
grep -q 'label = "应用字体"' "$MIUIX"
grep -q 'label = "查看详情"' "$MATERIAL"
grep -q 'label = "应用字体"' "$MATERIAL"
grep -q 'topActions()' "$MIUIX"
grep -q 'topActions()' "$MATERIAL"
grep -q 'topActions: @Composable' "$ROUTE"
grep -q 'embedded: Boolean = false' "$OVERLAY"
grep -q 'embedded = true' "$SHELL"
grep -q 'libraryDockClearance' "$SHELL"
grep -q 'if (page == AppPage.Studio)' "$SHELL"
! grep -q 'page == AppPage.Library || page == AppPage.Studio' "$SHELL"

MIUIX_CARD=$(sed -n '/private fun MiuixFontCard/,/private fun MiuixLibraryNotice/p' "$MIUIX")
printf '%s\n' "$MIUIX_CARD" | grep -q 'Arrangement.spacedBy(10.dp)'
printf '%s\n' "$MIUIX_CARD" | grep -q 'Modifier.weight(1f)'
printf '%s\n' "$MIUIX_CARD" | grep -q 'softWrap = false'
printf '%s\n' "$MIUIX_CARD" | grep -q 'MiuixCapabilityStrip(fontCapabilityLabel(font))'
printf '%s\n' "$MIUIX_CARD" | grep -q 'fontPreviewText(font, detailed = true)'
printf '%s\n' "$MIUIX_CARD" | grep -q 'maxLines = 2'
! printf '%s\n' "$MIUIX_CARD" | grep -q 'Spacer(Modifier.weight(1f))'

MATERIAL_CARD=$(sed -n '/private fun MaterialFontCard/,/private fun MaterialLibraryMessage/p' "$MATERIAL")
printf '%s\n' "$MATERIAL_CARD" | grep -q 'Arrangement.spacedBy(10.dp)'
printf '%s\n' "$MATERIAL_CARD" | grep -q 'Modifier.weight(1f)'
printf '%s\n' "$MATERIAL_CARD" | grep -q 'softWrap = false'
printf '%s\n' "$MATERIAL_CARD" | grep -q 'MaterialCapabilityStrip(fontCapabilityLabel(font))'
printf '%s\n' "$MATERIAL_CARD" | grep -q 'fontPreviewText(font, detailed = true)'
printf '%s\n' "$MATERIAL_CARD" | grep -q 'maxLines = 2'
! printf '%s\n' "$MATERIAL_CARD" | grep -q 'Spacer(Modifier.weight(1f))'

DOCK=$(sed -n '/private fun MiuixAppDock/,$p' "$SHELL")
printf '%s\n' "$DOCK" | grep -q 'height(54.dp)'
printf '%s\n' "$DOCK" | grep -q 'size(if (selected) 21.dp else 19.dp)'

echo 'Font library UI layout regression passed.'
