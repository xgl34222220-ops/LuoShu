#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
COMPACT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
HOME_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeRoute.kt"
HOME_COMPACT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeScreenCompact.kt"
LOGS_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsRoute.kt"
LOGS_COMPACT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenCompact.kt"
DIAGNOSTIC="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt"
STUDIO_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioRoute.kt"
STUDIO_TOOLS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt"
STUDIO_MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMiuix.kt"
STUDIO_MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMaterial.kt"
OVERLAY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"
SETTINGS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/AppearanceSettingsScreen.kt"

# Legacy style screens stay available as a rollback path while the routes use the
# shared compact hierarchy.
grep -q 'private fun MiuixCapabilityStrip' "$MIUIX"
grep -q 'private fun MaterialCapabilityStrip' "$MATERIAL"
grep -q 'FontLibraryScreenCompact' "$ROUTE"
grep -q 'HomeScreenCompact' "$HOME_ROUTE"
grep -q 'LogsScreenCompact' "$LOGS_ROUTE"

# Font library: management tools are collapsed, the card itself opens details,
# and the default row is compact rather than a 102 dp showcase card.
grep -q 'var showTools' "$COMPACT"
grep -q '导入与管理' "$COMPACT"
grep -q 'CompactFontRow' "$COMPACT"
grep -q 'NativeFontPreview' "$COMPACT"
grep -q 'clickable(onClick = onDetails)' "$COMPACT"
! grep -q 'height(102.dp)' "$COMPACT"

# Home: one dynamic next action replaces duplicate navigation shortcuts and the
# trust chip participates in normal layout rather than using a fixed 108 dp offset.
grep -q 'HomeNextStep' "$HOME_COMPACT"
grep -q '继续调整当前字体' "$HOME_COMPACT"
grep -q '打开任务中心查看错误原因' "$HOME_COMPACT"
! grep -q 'QUICK ACCESS' "$HOME_COMPACT"
! grep -q 'bottom = 108.dp' "$HOME_ROUTE"

# Task center separates user-facing tasks/issues from raw logs and its two header
# actions have the same 50 dp visual size.
grep -q 'enum class LogsTab' "$LOGS_COMPACT"
grep -q 'TASKS("任务")' "$LOGS_COMPACT"
grep -q 'ISSUES("问题")' "$LOGS_COMPACT"
grep -q 'LOGS("日志")' "$LOGS_COMPACT"
grep -q 'TaskPhase.FAILED' "$LOGS_COMPACT"
grep -q 'modifier = modifier.size(50.dp)' "$DIAGNOSTIC"
grep -q 'Modifier.size(50.dp)' "$LOGS_COMPACT"

# Studio uses one in-flow final action. Both title actions share one Row and the
# Studio viewport ends above the floating dock instead of drawing cards under it.
grep -q 'MiuixFinalAction(state, actions)' "$STUDIO_MIUIX"
grep -q 'MaterialFinalAction(state, actions)' "$STUDIO_MATERIAL"
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MIUIX"
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MATERIAL"
grep -q 'topAction()' "$STUDIO_MIUIX"
grep -q 'topAction()' "$STUDIO_MATERIAL"
grep -q 'bottom = 24.dp' "$STUDIO_MIUIX"
grep -q 'bottom = 24.dp' "$STUDIO_MATERIAL"
! grep -q 'align(Alignment.TopEnd)' "$STUDIO_ROUTE"
! grep -q 'statusBarsPadding()' "$STUDIO_ROUTE"
! grep -q 'navigationBarsPadding()' "$STUDIO_ROUTE"
grep -q 'shape = RoundedCornerShape(18.dp)' "$STUDIO_TOOLS"
! grep -q 'CircleShape' "$STUDIO_TOOLS"
! grep -q 'align(Alignment.BottomStart)' "$STUDIO_ROUTE"
! grep -q 'align(Alignment.BottomCenter)' "$STUDIO_ROUTE"
grep -q 'padding(bottom = dockClearance)' "$SHELL"

# Four-item dock, larger labels, hidden settings dock, Haze sampling and a real
# liquid-glass surface with refraction highlights instead of an opaque white card.
grep -q 'private val dockPages' "$SHELL"
[ "$(sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -c 'AppPage\.')" -eq 4 ]
grep -q 'if (page != AppPage.Settings)' "$SHELL"
grep -q 'fontSize = 11.sp' "$SHELL"
grep -q 'private fun MiuixAppDock' "$SHELL"
MIUIX_DOCK=$(sed -n '/private fun MiuixAppDock/,/private fun AppDockLayout/p' "$SHELL")
printf '%s\n' "$MIUIX_DOCK" | grep -q 'hazeEffect'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'blurRadius = 36.dp'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'activeGlass'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'drawRoundRect'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'indicatorBorderColor'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'indicatorShadow = 0.dp'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'scheme.primary.copy(alpha = if (dark) .30f else .20f)'
grep -q '底栏液态玻璃效果' "$SETTINGS"
grep -q '真实背景采样、折射高光与透明质感' "$SETTINGS"
grep -q 'embedded: Boolean = false' "$OVERLAY"
grep -q 'embedded = true' "$SHELL"
grep -q 'dockClearance' "$SHELL"
! grep -q 'if (page == AppPage.Studio)' "$SHELL"

echo 'LuoShu compact UI layout regression passed.'
