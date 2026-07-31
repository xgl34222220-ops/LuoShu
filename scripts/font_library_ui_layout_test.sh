#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
COMPACT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
HOME_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeRoute.kt"
HOME_COMPACT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeScreenCompact.kt"
ACCEPTANCE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceAcceptanceGuide.kt"
MATRIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceTestMatrix.kt"
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
THEME="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuTheme.kt"
COMPONENTS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/design/LuoShuComponents.kt"
UTIL="$ROOT/common/util_functions.sh"
CACHE="$ROOT/common/device_font_cache.sh"

# Legacy screens remain available while active routes use compact pages.
grep -q 'private fun MiuixCapabilityStrip' "$MIUIX"
grep -q 'private fun MaterialCapabilityStrip' "$MATERIAL"
grep -q 'FontLibraryScreenCompact' "$ROUTE"
grep -q 'HomeScreenCompact' "$HOME_ROUTE"
grep -q 'LogsScreenCompact' "$LOGS_ROUTE"

# Font library compact hierarchy.
grep -q 'var showTools' "$COMPACT"
grep -q '导入与管理' "$COMPACT"
grep -q 'CompactFontRow' "$COMPACT"
grep -q 'NativeFontPreview' "$COMPACT"
grep -q 'clickable(onClick = onDetails)' "$COMPACT"
! grep -q 'height(102.dp)' "$COMPACT"

# Home second pass is locked to the first real-device screenshot. The first pass
# was still oversized on the user's active font, so the card radius, rhythm,
# status orb and segmented bar are reduced while the dock clearance increases.
grep -q 'private val PagePadding = 12.dp' "$HOME_COMPACT"
grep -q 'private val CardRadius = 17.dp' "$HOME_COMPACT"
grep -q 'private val SectionGap = 7.dp' "$HOME_COMPACT"
grep -q 'bottom = 120.dp' "$HOME_COMPACT"
grep -q 'fontSize = 23.sp' "$HOME_COMPACT"
grep -q 'private fun EngineOverview' "$HOME_COMPACT"
grep -q 'private fun SegmentedAction' "$HOME_COMPACT"
grep -q 'fillMaxWidth().height(40.dp)' "$HOME_COMPACT"
grep -q 'size(54.dp)' "$HOME_COMPACT"
grep -q 'private fun CompactShortcut' "$HOME_COMPACT"
grep -q 'private fun StatusGrid' "$HOME_COMPACT"
grep -q 'private fun StatusPairRow' "$HOME_COMPACT"
grep -q 'height(42.dp).padding(horizontal = 9.dp)' "$HOME_COMPACT"
grep -q 'HomeNextStep' "$HOME_COMPACT"
grep -q '继续调整当前字体' "$HOME_COMPACT"
grep -q '打开任务中心查看错误与诊断信息' "$HOME_COMPACT"
! grep -q 'LuoShuPageHeader' "$HOME_COMPACT"
! grep -q 'LuoShuIconButton' "$HOME_COMPACT"
! grep -q 'size(88.dp)' "$HOME_COMPACT"
! grep -q 'QUICK ACCESS' "$HOME_COMPACT"

# The boot verification prompt must be an in-flow full-width row. The old
# floating chip produced a dark blurred blob and clipped subtitle on-device.
grep -q 'private fun HomeTrustRow' "$HOME_ROUTE"
grep -q 'modifier = Modifier.fillMaxWidth()' "$HOME_ROUTE"
grep -q 'shadowElevation = 0.dp' "$HOME_ROUTE"
grep -q 'fontSize = 10.5.sp' "$HOME_ROUTE"
! grep -q 'DeviceTrustChip(' "$HOME_ROUTE"
! grep -q 'bottom = 108.dp' "$HOME_ROUTE"

# Acceptance guidance follows the installed version and does not treat an
# unverified compatibility mapping as proof that the font is effective.
grep -q "targetVersion: String = state.version.substringBefore('-').substringBefore('+')" "$MATRIX"
grep -q '真机测试矩阵 · ${report.targetVersion}' "$MATRIX"
grep -q '测试矩阵与当前版本预发行门禁' "$ACCEPTANCE"
grep -q 'val blocking: Boolean = true' "$ACCEPTANCE"
grep -q '尚无系统实际加载证据，不能判定字体已经生效' "$ACCEPTANCE"
! grep -q '不影响正常使用' "$ACCEPTANCE"
grep -q '兼容映射尚未获得加载证据；设备对齐缓存仍在后台准备' "$ACCEPTANCE"
grep -q '加载验证失败，请打开问题页查看具体失败分区' "$ACCEPTANCE"
! grep -q 'v2.2.2' "$MATRIX"
! grep -q 'v2.2.2' "$ACCEPTANCE"

# ROM detection and detached cache worker contracts.
grep -q 'compact_rom_detection_logs' "$UTIL"
grep -q 'log_rom_detection_once coloros' "$UTIL"
grep -q 'log_rom_detection_once hyperos' "$UTIL"
grep -q 'device_font_transaction_guard.sh' "$CACHE"
grep -q 'mount_compat.sh' "$CACHE"
grep -q 'type luoshu_sync_mount_payload' "$CACHE"

# Task center is a right-side rounded sheet.
grep -q 'enum class LogsTab' "$LOGS_COMPACT"
grep -q 'TASKS("任务")' "$LOGS_COMPACT"
grep -q 'ISSUES("问题")' "$LOGS_COMPACT"
grep -q 'LOGS("日志")' "$LOGS_COMPACT"
grep -q 'TaskPhase.FAILED' "$LOGS_COMPACT"
grep -q 'modifier = modifier.size(50.dp)' "$DIAGNOSTIC"
grep -q 'LuoShuIconButton' "$LOGS_COMPACT"
grep -q 'onClose: (() -> Unit)? = null' "$LOGS_ROUTE"
grep -q 'LuoShuSideSheet' "$SHELL"
grep -q 'logsSheetVisible' "$SHELL"

# Studio keeps one in-flow final action and clears the floating dock.
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
grep -q 'RoundedCornerShape(22.dp)' "$STUDIO_MIUIX"
grep -q 'RoundedCornerShape(22.dp)' "$STUDIO_MATERIAL"

# Shared tokens and components remain available to the remaining pages.
grep -q 'data class LuoShuTokens' "$THEME"
grep -q 'pageBackground = Color(0xFFECEBFA)' "$THEME"
grep -q 'dark -> Color(0xFF11131A)' "$THEME"
grep -q 'pureBlack -> Color.Black' "$THEME"
grep -q 'val pagePadding: Dp = 12.dp' "$THEME"
grep -q 'val groupRadius: Dp = 18.dp' "$THEME"
grep -q 'val dockRadius: Dp = 32.dp' "$THEME"
grep -q 'fun LuoShuPageHeader' "$COMPONENTS"
grep -q 'fun LuoShuGroupCard' "$COMPONENTS"
grep -q 'fun LuoShuSettingRow' "$COMPONENTS"
grep -q 'fun LuoShuSideSheet' "$COMPONENTS"
grep -q 'val sheetWidth = maxWidth \* .94f' "$COMPONENTS"
grep -q 'topStart = tokens.sideSheetRadius' "$COMPONENTS"
grep -q 'tween(300, easing = LuoShuEnterEasing)' "$COMPONENTS"
grep -q 'LuoShuPageHeader' "$COMPACT"
grep -q 'LuoShuPageHeader' "$STUDIO_MIUIX"
grep -q 'LuoShuPageHeader' "$STUDIO_MATERIAL"

# Four stable primary destinations and glass dock behavior.
grep -q 'private val dockPages' "$SHELL"
[ "$(sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -c 'AppPage\.')" -eq 4 ]
grep -q 'Settings("设置", Icons.Rounded.Settings)' "$SHELL"
! grep -q 'Logs("' "$SHELL"
grep -q 'if (!logsSheetVisible && !settingsThemeOpen)' "$SHELL"
grep -q 'targetValue = if (logsSheetVisible) (-12).dp else 0.dp' "$SHELL"
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

# Settings and native import hierarchy remain intact.
grep -q 'showThemeSettings: Boolean = false' "$SETTINGS"
grep -q 'ThemeSettingsPage' "$SETTINGS"
grep -q 'title = "主题设置"' "$SETTINGS"
grep -q 'title = "任务中心"' "$SETTINGS"
grep -q 'title = "使用 Monet 取色"' "$SETTINGS"
grep -q 'title = "纯黑模式"' "$SETTINGS"
grep -q 'title = "玻璃效果"' "$SETTINGS"
grep -q 'title = "悬浮玻璃底栏"' "$SETTINGS"
grep -q 'MIUIX × Material 3 × Monet × Glass' "$SETTINGS"
grep -q 'embedded: Boolean = false' "$OVERLAY"
grep -q 'embedded = true' "$SHELL"
grep -q 'dockClearance' "$SHELL"
! grep -q 'if (page == AppPage.Studio)' "$SHELL"

echo 'LuoShu real-device home UI layout regression passed.'
