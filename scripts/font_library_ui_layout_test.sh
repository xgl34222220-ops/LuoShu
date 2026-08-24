#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
MATERIAL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMaterial.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
COMPACT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
DETAILS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontDetailsDialog.kt"
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
SETTINGS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SettingsHubScreen.kt"
ICON_SYSTEM="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
COMPACT_LAYOUT="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuCompactLayout.kt"
THEME="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuTheme.kt"
DOCK_INSETS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/DockInsets.kt"
APP_BRIDGE="$ROOT/common/app_bridge.sh"
UTIL="$ROOT/common/util_functions_core.sh"
CACHE="$ROOT/common/device_font_cache.sh"

# Legacy style screens stay available as a rollback path while the routes use the
# shared compact hierarchy.
grep -q 'private fun MiuixCapabilityStrip' "$MIUIX"
grep -q 'private fun MaterialCapabilityStrip' "$MATERIAL"
grep -q 'FontLibraryScreenCompact' "$ROUTE"
grep -q 'HomeScreenCompact' "$HOME_ROUTE"
grep -q 'LogsScreenCompact' "$LOGS_ROUTE"

# Font library: management tools are collapsed, the card itself opens details,
# preview glyphs use one Aa12 contract, and detail viewing is a stable large preview sheet.
grep -q 'var showTools' "$COMPACT"
grep -q 'Text(if (showTools) "收起管理" else "管理")' "$COMPACT"
grep -q 'CompactFontRow' "$COMPACT"
grep -q 'NativeFontPreview' "$COMPACT"
grep -q 'clickable(onClick = onDetails)' "$COMPACT"
[ "$(grep -c '"Aa12"' "$COMPACT")" -ge 3 ]
! grep -q '"Aa 12"' "$COMPACT"
! grep -q '点击卡片查看完整预览与字体信息' "$COMPACT"
grep -q 'FontLibraryBadge' "$COMPACT"
grep -q 'fontPrimaryBadge' "$COMPACT"
! grep -q 'height(102.dp)' "$COMPACT"
! grep -q '轻触卡片预览' "$COMPACT"
grep -q 'modifier = Modifier.size(44.dp)' "$COMPACT"
grep -q 'ModalBottomSheet' "$DETAILS"
grep -q 'sheetGesturesEnabled = false' "$DETAILS"
grep -q 'fillMaxHeight(0.94f)' "$DETAILS"
grep -q 'dragHandle = null' "$DETAILS"
grep -q 'detailScrollState.scrollTo(0)' "$DETAILS"
! grep -q 'heightIn(max = 760.dp)' "$DETAILS"
grep -q 'FontPreviewMode' "$DETAILS"
grep -q 'PreviewModeChip' "$DETAILS"
grep -q '花间一壶酒' "$DETAILS"
grep -q 'LuoShu Aa 0123456789' "$DETAILS"
grep -q '应用此字体' "$DETAILS"
! grep -q 'AlertDialog' "$DETAILS"

# Home: one dynamic next action replaces duplicate navigation shortcuts and the
# trust chip participates in normal layout rather than using a fixed 108 dp offset.
grep -q 'HomeNextStep' "$HOME_COMPACT"
grep -q '继续调整当前字体' "$HOME_COMPACT"
grep -q '打开任务中心查看错误原因' "$HOME_COMPACT"
! grep -q 'QUICK ACCESS' "$HOME_COMPACT"
! grep -q 'bottom = 108.dp' "$HOME_ROUTE"
grep -q 'LuoShuTopBar(title = "洛书")' "$HOME_COMPACT"
! grep -q 'FONT ENGINE' "$HOME_COMPACT"
! grep -q 'FONT LIBRARY' "$COMPACT"
! grep -q 'TASK CENTER' "$LOGS_COMPACT"

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

# Task center separates user-facing tasks/issues from raw logs and all routed header
# actions use the same compact visible box while preserving a 48 dp touch target.
grep -q 'enum class LogsTab' "$LOGS_COMPACT"
grep -q 'TASKS("任务")' "$LOGS_COMPACT"
grep -q 'ISSUES("问题")' "$LOGS_COMPACT"
grep -q 'LOGS("日志")' "$LOGS_COMPACT"
grep -q 'TaskPhase.FAILED' "$LOGS_COMPACT"
grep -q 'LuoShuHeaderAction' "$DIAGNOSTIC"
grep -q 'LuoShuHeaderAction' "$LOGS_COMPACT"
! grep -q 'Modifier.size(50.dp)' "$LOGS_COMPACT"

# Studio uses one in-flow final action. Both title actions share one Row and the
# Studio viewport keeps its local padding while the shell lets glass overlap the final content.
grep -q 'MiuixFinalAction(state, actions)' "$STUDIO_MIUIX"
grep -q 'MaterialFinalAction(state, actions)' "$STUDIO_MATERIAL"
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MIUIX"
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MATERIAL"
grep -q 'topAction()' "$STUDIO_MIUIX"
grep -q 'topAction()' "$STUDIO_MATERIAL"
grep -q 'LuoShuTopBar(title = "字体组合")' "$STUDIO_MIUIX"
! grep -q 'FONT MIX' "$STUDIO_MIUIX"
grep -q 'fontSize = 30.sp' "$STUDIO_MATERIAL"
grep -q 'horizontalArrangement = Arrangement.spacedBy(0.dp)' "$STUDIO_MIUIX"
grep -q 'horizontalArrangement = Arrangement.spacedBy(6.dp)' "$STUDIO_MATERIAL"
grep -q 'contentColor = actionColor' "$STUDIO_MIUIX"
grep -q 'contentColor = actionColor' "$STUDIO_MATERIAL"
grep -q 'LuoShuHeaderAction' "$STUDIO_MATERIAL"
! grep -q 'modifier = Modifier.size(56.dp)' "$STUDIO_MATERIAL"
grep -q 'maxOf(LocalDockContentPadding.current, 24.dp)' "$STUDIO_MIUIX"
grep -q 'bottom = 24.dp' "$STUDIO_MATERIAL"
! grep -q 'align(Alignment.TopEnd)' "$STUDIO_ROUTE"
! grep -q 'statusBarsPadding()' "$STUDIO_ROUTE"
! grep -q 'navigationBarsPadding()' "$STUDIO_ROUTE"
grep -q 'LuoShuHeaderAction' "$STUDIO_TOOLS"
grep -q 'opticalScale = 1.08f' "$STUDIO_TOOLS"
! grep -q 'modifier = modifier.size(56.dp)' "$STUDIO_TOOLS"
! grep -q 'align(Alignment.BottomStart)' "$STUDIO_ROUTE"
! grep -q 'align(Alignment.BottomCenter)' "$STUDIO_ROUTE"
[ "$(grep -c 'padding(bottom = dockClearance)' "$SHELL")" -eq 5 ]
grep -q 'val edgeToEdgeGlass = appearance.uiStyle == UiStyle.MIUIX' "$SHELL"
grep -q 'edgeToEdgeGlass -> 0.dp' "$SHELL"
grep -q 'navigationBottom + 78.dp' "$SHELL"
[ "$(grep -c 'LocalDockContentPadding provides dockContentPadding' "$SHELL")" -eq 5 ]
grep -q 'LocalDockContentPadding' "$DOCK_INSETS"

# Four-item dock maps the primary product areas directly, keeps tasks as a detail page,
# and limits glass to one quiet Haze surface with a flat tinted selection indicator.
grep -q 'private val dockPages' "$SHELL"
[ "$(sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -c 'AppPage\.')" -eq 4 ]
sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -q 'AppPage.Settings'
! sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -q 'AppPage.Logs'
grep -q 'val showDock = page != AppPage.Logs' "$SHELL"
grep -q 'fontSize = 10.sp' "$SHELL"
grep -q 'LuoShuIconTokens.DockGlyph' "$SHELL"
! grep -q 'targetValue = if (selected) 21.dp else 19.dp' "$SHELL"
grep -q 'private fun MiuixAppDock' "$SHELL"
MIUIX_DOCK=$(sed -n '/private fun MiuixAppDock/,/private fun AppDockLayout/p' "$SHELL")
printf '%s\n' "$MIUIX_DOCK" | grep -q 'hazeEffect'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'blurRadius = 20.dp'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'noiseFactor = .008f'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'RoundedCornerShape(27.dp)'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'activeGlass'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'Color.White.copy(alpha = .62f)'
! printf '%s\n' "$MIUIX_DOCK" | grep -q 'drawRoundRect'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'indicatorColor = scheme.primary.copy'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'indicatorShadow = 0.dp'
! printf '%s\n' "$MIUIX_DOCK" | grep -q 'liquidLens'
! printf '%s\n' "$MIUIX_DOCK" | grep -q 'blurRadius = 36.dp'
! printf '%s\n' "$MIUIX_DOCK" | grep -q 'blurRadius = 30.dp'
! grep -q -- '-> 34.dp' "$SHELL"
grep -q 'collectIsPressedAsState' "$SHELL"
grep -q 'baseItemColor.copy(alpha = .62f)' "$SHELL"
grep -q 'offscreen buffer inside the Haze surface' "$SHELL"
! grep -q 'luoshuDockItemScale' "$SHELL"
! grep -q 'graphicsLayer' "$SHELL"
grep -q 'dampingRatio = .84f' "$SHELL"

# Settings follows a grouped home -> detail hierarchy instead of a clipped horizontal tab strip.
grep -q 'SettingCard("视觉与显示")' "$SETTINGS"
grep -q 'ToggleLine("玻璃半透明", "用于悬浮底栏和弹层，内容卡片保持清晰"' "$SETTINGS"
grep -q 'ToggleLine("背景模糊", "模糊底栏后方经过的内容"' "$SETTINGS"
grep -q 'ToggleLine("悬浮底栏", "关闭后贴合屏幕底部"' "$SETTINGS"
grep -q 'private fun SettingsGroup' "$SETTINGS"
grep -q 'private fun SettingsNavigationRow' "$SETTINGS"
grep -q 'settingsDetailTransition' "$SETTINGS"
grep -q 'LuoShuDetailBar' "$SETTINGS"
! grep -q 'Modifier.width(70.dp)' "$SETTINGS"
grep -q 'embedded: Boolean = false' "$OVERLAY"
grep -q 'embedded = true' "$SHELL"
grep -q 'dockClearance' "$SHELL"
grep -q 'val HeaderTouchTarget = 48.dp' "$ICON_SYSTEM"
grep -q 'val HeaderContainer = 30.dp' "$ICON_SYSTEM"
grep -q 'val HeaderGlyph = 17.dp' "$ICON_SYSTEM"
grep -q 'IconButtonDefaults.iconButtonColors' "$ICON_SYSTEM"
grep -q 'val DockGlyph = 19.dp' "$ICON_SYSTEM"
grep -q 'val SectionGlyph = 18.dp' "$ICON_SYSTEM"
grep -q 'val ToolGlyph = 20.dp' "$ICON_SYSTEM"
grep -q 'maxOf(LocalDockContentPadding.current, 24.dp)' "$HOME_COMPACT"
grep -q 'maxOf(LocalDockContentPadding.current, 28.dp)' "$COMPACT"
grep -q 'maxOf(LocalDockContentPadding.current, 24.dp)' "$LOGS_COMPACT"
grep -q 'CompactStatusCell' "$HOME_COMPACT"
grep -q "self-mount) printf '洛书自挂载'" "$APP_BRIDGE"
grep -q 'mountSummary(h)' "$SETTINGS"
grep -q 'selfMountSummary(h)' "$SETTINGS"
grep -q 'RoundedCornerShape(22.dp)' "$SETTINGS"
grep -q 'pageBackground = Color(0xFFF5F3FC)' "$THEME"
grep -q 'internal fun LuoShuTopBar' "$COMPACT_LAYOUT"
grep -q 'internal fun LuoShuDetailBar' "$COMPACT_LAYOUT"
grep -q 'itemsIndexed(state.tasks' "$LOGS_COMPACT"
grep -q 'Box(Modifier.size(10.dp).background(color, CircleShape))' "$LOGS_COMPACT"
grep -q 'isLast: Boolean' "$LOGS_COMPACT"
! grep -q 'padding(bottom = 96.dp)' "$LOGS_ROUTE"
! grep -q 'if (page == AppPage.Studio)' "$SHELL"

echo 'LuoShu compact UI layout regression passed.'
