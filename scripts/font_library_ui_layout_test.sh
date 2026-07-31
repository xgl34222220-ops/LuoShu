#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
THEME="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuTheme.kt"
COMPONENTS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/design/LuoShuComponents.kt"
HOME="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeScreenCompact.kt"
TRUST="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceTrustUi.kt"
LIBRARY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
LIB_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
MONITOR="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontDirectoryMonitor.kt"
BACKUP="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryBackup.kt"
ARCHIVE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontArchiveExport.kt"
MANAGEMENT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryManagement.kt"
IMPORT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
INSPECTOR="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/FontMetadataInspector.kt"
STUDIO_MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMiuix.kt"
STUDIO_MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt"
STUDIO_TOOLS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt"
SETTINGS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/AppearanceSettingsScreen.kt"

# Video-accurate compact foundation: restrained lavender-grey background, smaller typography,
# one button specification and lower visual weight.
grep -q 'pageBackground = Color(0xFFF3F2FA)' "$THEME"
grep -q 'headlineLarge = TextStyle(fontSize = 24.sp' "$THEME"
grep -q 'val groupRadius: Dp = 22.dp' "$THEME"
grep -q 'modifier = modifier.size(48.dp)' "$COMPONENTS"
grep -q 'shape = RoundedCornerShape(16.dp)' "$COMPONENTS"
grep -q 'shadowElevation = 1.dp' "$COMPONENTS"
grep -q 'heightIn(min = 72.dp)' "$COMPONENTS"
grep -q 'Box(Modifier.align(Alignment.Center)' "$COMPONENTS"
grep -q 'defaultMinSize(minHeight = 56.dp)' "$COMPONENTS"

# No decorative or page-specific top button dimensions. Studio tools and refresh use the same
# LuoShuIconButton component, and settings no longer displays a non-clickable oversized gear tile.
grep -q 'LuoShuIconButton(' "$STUDIO_TOOLS"
grep -q 'modifier = modifier,' "$STUDIO_TOOLS"
! grep -q 'modifier = modifier.size(56.dp)' "$STUDIO_TOOLS"
! sed -n '/title = "设置"/,/item { LuoShuSectionTitle/p' "$SETTINGS" | grep -q 'Icons.Rounded.Settings'

# Home is a compact status page rather than a hero dashboard with a giant status orb.
grep -q 'private fun EngineStatusCard' "$HOME"
grep -q 'LuoShuSettingRow(' "$HOME"
grep -q 'height(44.dp)' "$HOME"
! grep -q 'private fun StatusOrb' "$HOME"
grep -q 'shadowElevation = 0.dp' "$TRUST"

# Font library keeps tools collapsed, uses compact search/filter/list rows and neutral management
# surfaces instead of unrelated blue/pink dashboard blocks.
grep -q 'var showTools' "$LIBRARY"
grep -q 'Modifier.fillMaxWidth().height(52.dp)' "$LIBRARY"
grep -q 'shape = RoundedCornerShape(20.dp)' "$LIBRARY"
grep -q 'modifier = Modifier.size(44.dp)' "$LIBRARY"
grep -q 'tools = managementTools' "$LIB_ROUTE"
for file in "$MONITOR" "$BACKUP" "$ARCHIVE" "$MANAGEMENT"; do
    grep -q 'color = MaterialTheme.colorScheme.surfaceContainerLow' "$file"
done
grep -q 'shape = RoundedCornerShape(20.dp)' "$IMPORT"
grep -q 'modifier = modifier.size(48.dp)' "$INSPECTOR"

# Studio pages reserve space for the dock, reduce oversized cards and keep both top actions at the
# exact shared size.
grep -q 'bottom = 18.dp' "$STUDIO_MIUIX"
grep -q 'bottom = 18.dp' "$STUDIO_MATERIAL"
grep -q 'LuoShuIconButton(' "$STUDIO_MIUIX"
grep -q 'LuoShuIconButton(' "$STUDIO_MATERIAL"
! grep -q 'Spacer(Modifier.width(6.dp))' "$STUDIO_MIUIX"
! grep -q 'Spacer(Modifier.width(6.dp))' "$STUDIO_MATERIAL"

# Four stable primary destinations with a thinner floating dock and subtle selected indicator.
grep -q 'private val dockPages' "$SHELL"
[ "$(sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -c 'AppPage\.')" -eq 4 ]
grep -q 'itemHeight = 50.dp' "$SHELL"
grep -q 'dockClearance = navigationBottom + if (appearance.floatingDock) 70.dp else 58.dp' "$SHELL"
grep -q 'shadow(if (floating) 7.dp else 3.dp' "$SHELL"
grep -q 'background(unified.pageBackground)' "$SHELL"

# Core functionality remains routed through the shared compact pages and right-side task sheet.
grep -q 'HomeScreenCompact' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeRoute.kt"
grep -q 'FontLibraryScreenCompact' "$LIB_ROUTE"
grep -q 'LuoShuSideSheet' "$SHELL"
grep -q 'logsSheetVisible' "$SHELL"

echo 'LuoShu video-accurate compact UI regression passed.'
