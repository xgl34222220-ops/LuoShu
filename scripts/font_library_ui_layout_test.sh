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

# Font library now has two independent render trees. The Miuix implementation
# must use native Miuix controls and must not import Material 3 components.
grep -q 'top.yukonga.miuix.kmp.basic.BasicComponent' "$MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.TextField' "$MIUIX"
grep -q 'top.yukonga.miuix.kmp.theme.MiuixTheme' "$MIUIX"
! grep -q 'androidx.compose.material3' "$MIUIX"
grep -q 'UiStyle.MIUIX -> FontLibraryScreenMiuix' "$ROUTE"
grep -q 'UiStyle.MATERIAL -> FontLibraryScreenCompact' "$ROUTE"
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
grep -q 'var showTools by rememberSaveable' "$MIUIX"
grep -q '导入与管理' "$MIUIX"
grep -q 'MiuixFontFamilyCard' "$MIUIX"
grep -q 'NativeFontPreview' "$MIUIX"

# Home: one dynamic next action replaces duplicate navigation shortcuts and the
# trust chip participates in normal layout rather than using a fixed 108 dp offset.
grep -q 'HomeNextStep' "$HOME_COMPACT"
grep -q '继续调整当前字体' "$HOME_COMPACT"
grep -q '打开任务中心查看错误原因' "$HOME_COMPACT"
! grep -q 'QUICK ACCESS' "$HOME_COMPACT"
! grep -q 'bottom = 108.dp' "$HOME_ROUTE"

# Acceptance guidance follows the installed version and never treats an
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

# ROM detection is a state fact, not a polling log. Existing duplicate records
# are compacted once and new entries are emitted only when the detected version changes.
grep -q 'compact_rom_detection_logs' "$UTIL"
grep -q 'log_rom_detection_once coloros' "$UTIL"
grep -q 'log_rom_detection_once hyperos' "$UTIL"

# A detached background cache worker must load the transaction and mount layers
# itself before activating a generated payload.
grep -q 'device_font_transaction_guard.sh' "$CACHE"
grep -q 'mount_compat.sh' "$CACHE"
grep -q 'type luoshu_sync_mount_payload' "$CACHE"

# Task center separates user-facing tasks/issues from raw logs. It is opened as
# a right-side rounded sheet and uses the common 48 dp icon-button hit target.
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

# Studio uses one in-flow final action. Both title actions share one Row and the
# viewport ends above the floating dock instead of drawing cards under it.
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

# Unified design system remains available to legacy Material pages while the
# Miuix pages migrate to their own native component tree.
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
grep -q 'LuoShuPageHeader' "$HOME_COMPACT"
grep -q 'LuoShuPageHeader' "$COMPACT"
grep -q 'LuoShuPageHeader' "$STUDIO_MIUIX"
grep -q 'LuoShuPageHeader' "$STUDIO_MATERIAL"

# Four stable primary destinations. Settings stays in the dock; task/log details
# and nested theme settings temporarily hide it and preserve the underlay.
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

# Settings is a grouped overview plus a nested animated theme page. All style,
# Monet, dark, pure-black and glass options stay in one shared page hierarchy.
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

echo 'LuoShu separate Miuix and Material UI layout regression passed.'
