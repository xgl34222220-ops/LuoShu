#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenMiuix.kt"
ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryRoute.kt"
DETAILS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontDetailsDialog.kt"
HOME_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeRoute.kt"
HOME_MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeScreenMiuix.kt"
ACCEPTANCE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceAcceptanceGuide.kt"
MATRIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceTestMatrix.kt"
LOGS_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsRoute.kt"
LOGS_MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenMiuix.kt"
DIAGNOSTIC="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt"
STUDIO_ROUTE="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioRoute.kt"
STUDIO_TOOLS="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt"
STUDIO_MIUIX="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioScreenMiuix.kt"
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

# Production routes use the only maintained MIUIx hierarchy.
grep -q 'private fun MiuixFontRow' "$MIUIX"
grep -q 'FontLibraryScreenMiuix' "$ROUTE"
grep -q 'StaggeredManagementItem(index = 0)' "$ROUTE"
grep -q 'StaggeredManagementItem(index = 1)' "$ROUTE"
grep -q 'StaggeredManagementItem(index = 2)' "$ROUTE"
grep -q 'StaggeredManagementItem(index = 3)' "$ROUTE"
grep -q 'index.coerceAtLeast(0) \* 30' "$ROUTE"
grep -q 'HomeScreenMiuix' "$HOME_ROUTE"
grep -q 'LogsScreenMiuix' "$LOGS_ROUTE"

# Font library: management tools are collapsed, the card itself opens details,
# each card has one readable native preview, and detail viewing is a stable large preview sheet.
grep -q 'var showTools' "$MIUIX"
grep -q '导入与管理' "$MIUIX"
grep -q 'MiuixFontRow' "$MIUIX"
grep -q 'NativeFontPreview' "$MIUIX"
grep -q 'onClick = onDetails' "$MIUIX"
grep -q '山海有相逢 Aa 0123' "$MIUIX"
grep -q 'Hello, LuoShu 0123' "$MIUIX"
! grep -q '"Aa 12"' "$MIUIX"
! grep -q '点击卡片查看完整预览与字体信息' "$MIUIX"
grep -q 'fontMetadataSummary' "$MIUIX"
grep -q 'glassOutlineBrush' "$MIUIX"
grep -q 'tokens.textSecondary' "$MIUIX"
grep -q '轻触卡片查看详情' "$MIUIX"
! grep -q 'height(102.dp)' "$MIUIX"
! grep -q '轻触卡片预览' "$MIUIX"
grep -q 'modifier = Modifier.heightIn(min = 44.dp)' "$MIUIX"
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

# Home keeps one state-aware primary action, font shortcuts, and collapsible device details.
# The trust chip participates in normal layout rather than using a fixed offset.
grep -q 'HomeNextStep' "$HOME_MIUIX"
grep -q '继续调整当前字体' "$HOME_MIUIX"
grep -q '打开任务中心查看错误原因' "$HOME_MIUIX"
! grep -q 'QUICK ACCESS' "$HOME_MIUIX"
! grep -q 'bottom = 108.dp' "$HOME_ROUTE"
grep -q 'LuoShuTopBar(title = "洛书")' "$HOME_MIUIX"
! grep -q 'FONT ENGINE' "$HOME_MIUIX"
! grep -q 'FONT LIBRARY' "$MIUIX"
! grep -q 'TASK CENTER' "$LOGS_MIUIX"

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

# A detached background cache worker is preparation-only. It may publish an immutable
# ready cache, but activation, reboot markers and transaction commits belong exclusively
# to the explicit foreground switch.
CACHE_WORKER=$(sed -n '/^_dfcache_build_pending_inner()/,/^}/p' "$CACHE")
printf '%s\n' "$CACHE_WORKER" | grep -q 'LUOSHU_CACHE_FOREGROUND'
! printf '%s\n' "$CACHE_WORKER" | grep -q 'device_font_cache_activate'
! printf '%s\n' "$CACHE_WORKER" | grep -q 'text_reboot_required.conf'
! printf '%s\n' "$CACHE_WORKER" | grep -q 'luoshu_payload_transaction_commit'
grep -q '设备对齐缓存已就绪且未改动当前字体' "$CACHE"

# Task center separates user-facing tasks/issues from raw logs and all routed header
# actions use the same compact visible box while preserving a 48 dp touch target.
grep -q 'enum class LogsTab' "$LOGS_MIUIX"
grep -q 'TASKS("任务")' "$LOGS_MIUIX"
grep -q 'ISSUES("问题")' "$LOGS_MIUIX"
grep -q 'LOGS("日志")' "$LOGS_MIUIX"
grep -q 'TaskPhase.FAILED' "$LOGS_MIUIX"
grep -q 'LuoShuHeaderAction' "$DIAGNOSTIC"
grep -q 'LuoShuHeaderAction' "$LOGS_MIUIX"
! grep -q 'Modifier.size(50.dp)' "$LOGS_MIUIX"

# Studio uses one in-flow final action. Both title actions share one Row. The
# shell now also owns the directional page motion and Quick Return dock clearance
# so long lists regain viewport space while the frosted dock keeps its overlap behavior.
grep -q 'MiuixFinalAction(state, actions)' "$STUDIO_MIUIX"
grep -q 'topAction: @Composable () -> Unit' "$STUDIO_MIUIX"
grep -q 'topAction()' "$STUDIO_MIUIX"
grep -q 'LuoShuTopBar(title = "字体组合")' "$STUDIO_MIUIX"
! grep -q 'FONT MIX' "$STUDIO_MIUIX"
grep -q 'horizontalArrangement = Arrangement.spacedBy(0.dp)' "$STUDIO_MIUIX"
grep -q 'contentColor = actionColor' "$STUDIO_MIUIX"
grep -q 'InteractiveAxisSlider' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioAxisControls.kt"
grep -q 'height(72.dp)' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioAxisControls.kt"
grep -q 'LuoShuLayoutTokens.FloatingDockSafeBottom' "$STUDIO_MIUIX"
! grep -q 'align(Alignment.TopEnd)' "$STUDIO_ROUTE"
! grep -q 'statusBarsPadding()' "$STUDIO_ROUTE"
! grep -q 'navigationBarsPadding()' "$STUDIO_ROUTE"
grep -q 'LuoShuHeaderAction' "$STUDIO_TOOLS"
grep -q 'opticalScale = 1.08f' "$STUDIO_TOOLS"
! grep -q 'modifier = modifier.size(56.dp)' "$STUDIO_TOOLS"
! grep -q 'align(Alignment.BottomStart)' "$STUDIO_ROUTE"
! grep -q 'align(Alignment.BottomCenter)' "$STUDIO_ROUTE"
[ "$(grep -c 'padding(bottom = dockClearance)' "$SHELL")" -eq 5 ]
grep -q 'val edgeToEdgeGlass = appearance.glassEnabled && appearance.floatingDock && showDock' "$SHELL"
grep -q 'edgeToEdgeGlass -> 0.dp' "$SHELL"
grep -q 'navigationBottom + 94.dp' "$SHELL"
grep -q 'val dockPaddingTarget = if (edgeToEdgeGlass)' "$SHELL"
grep -q 'if (dockHiddenByScroll) 28.dp else 108.dp' "$SHELL"
grep -q 'Modifier.nestedScroll(dockScrollConnection)' "$SHELL"
grep -q 'dockHideThresholdPx' "$SHELL"
grep -q 'dockShowThresholdPx' "$SHELL"
# Only direct user intent drives Quick Return. Capturing the page backdrop stays
# enabled until the existing enter/exit transition has actually finished.
grep -q 'userInput = source == NestedScrollSource.UserInput' "$SHELL"
grep -q 'dockScrollPolicy.finishGesture()' "$SHELL"
grep -q 'Lifecycle.Event.ON_RESUME' "$SHELL"
grep -q 'dockScrollPolicy.reset()' "$SHELL"
grep -q 'visibleState = dockVisibility' "$SHELL"
grep -q 'currentVisible = dockVisibility.currentState' "$SHELL"
grep -q 'targetVisible = dockVisibility.targetState' "$SHELL"
grep -q 'transitionIdle = dockVisibility.isIdle' "$SHELL"
grep -q 'val blurActive = appearance.blurEnabled && appearance.glassEnabled && dockCaptureRequired' "$SHELL"
grep -q 'val dockHideThresholdPx = with(density) { 34.dp.toPx() }' "$SHELL"
grep -q 'val dockShowThresholdPx = with(density) { 6.dp.toPx() }' "$SHELL"
if grep -q 'dockScrollAccumulator' "$SHELL"; then
  echo 'Quick Return must keep per-scroll accumulation outside Compose state.' >&2
  exit 1
fi
[ "$(grep -c 'LocalDockContentPadding provides dockContentPadding' "$SHELL")" -eq 5 ]
grep -q 'LocalDockContentPadding' "$DOCK_INSETS"

# Four-item dock maps the primary product areas directly and keeps tasks as a detail page. The
# Miuix variant uses the reference-style frosted shell plus a separate animated liquid lens.
grep -q 'private val dockPages' "$SHELL"
[ "$(sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -c 'AppPage\.')" -eq 4 ]
sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -q 'AppPage.Settings'
! sed -n '/private val dockPages = listOf(/,/^)/p' "$SHELL" | grep -q 'AppPage.Logs'
grep -q 'val showDock = page != AppPage.Logs' "$SHELL"
grep -q 'fontSize = 12.sp' "$SHELL"
grep -q 'LuoShuIconTokens.DockGlyph' "$SHELL"
! grep -q 'targetValue = if (selected) 21.dp else 19.dp' "$SHELL"
grep -q 'private fun MiuixAppDock' "$SHELL"
MIUIX_DOCK=$(sed -n '/private fun MiuixAppDock/,/private fun AppDockLayout/p' "$SHELL")
printf '%s\n' "$MIUIX_DOCK" | grep -q 'hazeEffect'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'blurRadius = 30.dp'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'noiseFactor = .018f'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'RoundedCornerShape(31.dp)'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'activeGlass'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'Color.White.copy(alpha = .22f)'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'drawRoundRect'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'indicatorColor = scheme.primary.copy'
! grep -q 'indicatorShadow' "$SHELL"
printf '%s\n' "$MIUIX_DOCK" | grep -q 'itemHeight = 60.dp'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'runtimeLiquid'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'Modifier.layerBackdrop(dockSurfaceBackdrop)'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'Modifier.drawBackdrop'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'liquidGlassLens'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'indicatorBackdrop = dockSurfaceBackdrop'
printf '%s\n' "$MIUIX_DOCK" | grep -q 'liquidGlass = activeGlass'
! grep -q -- '-> 34.dp' "$SHELL"
grep -q 'collectIsPressedAsState' "$SHELL"
grep -q 'baseItemColor.copy(alpha = .62f)' "$SHELL"
! grep -q 'luoshuDockItemScale' "$SHELL"
grep -q 'Three independent layers mirror the reference implementation' "$SHELL"
grep -q 'graphicsLayer' "$SHELL"
grep -q 'dampingRatio = if (liquidGlass) .82f else .90f' "$SHELL"
grep -q 'liquidStretch.animateTo' "$SHELL"
grep -q 'AnimatedVisibility(' "$SHELL"
grep -q 'pageStateHolder.SaveableStateProvider(page.name)' "$SHELL"
grep -q 'translationX = (1f - pageEnter.value) \* 14.dp.toPx() \* pageDirection' "$SHELL"
grep -q 'page.motionIndex() - previousPageForMotion.motionIndex()' "$SHELL"
! grep -q 'AnimatedContent' "$SHELL"

# Settings follows a grouped home -> detail hierarchy instead of a clipped horizontal tab strip.
grep -q 'SettingCard("视觉与显示")' "$SETTINGS"
grep -q 'ToggleLine("玻璃半透明", "柔和透光的卡片、悬浮底栏与弹层"' "$SETTINGS"
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
grep -q 'val HeaderContainer = 44.dp' "$ICON_SYSTEM"
grep -q 'val HeaderGlyph = 21.dp' "$ICON_SYSTEM"
grep -q 'IconButtonDefaults.iconButtonColors' "$ICON_SYSTEM"
grep -q 'val DockGlyph = 22.dp' "$ICON_SYSTEM"
grep -q 'val SectionGlyph = 18.dp' "$ICON_SYSTEM"
grep -q 'val ToolGlyph = 20.dp' "$ICON_SYSTEM"
grep -q 'LuoShuLayoutTokens.FloatingDockSafeBottom' "$HOME_MIUIX"
grep -q 'LuoShuLayoutTokens.FloatingDockSafeBottom' "$MIUIX"
# Logs is a detail route without a dock; reserve the measured import controls instead.
grep -q 'controlsBottomPadding + 28.dp' "$LOGS_MIUIX"
grep -q 'onSizeChanged { importControlsHeight = it.height }' "$LOGS_ROUTE"
grep -q 'MiuixStatusCell' "$HOME_MIUIX"
grep -q "self-mount) printf '洛书自挂载'" "$APP_BRIDGE"
grep -q 'mountSummary(h)' "$SETTINGS"
grep -q 'selfMountSummary(h)' "$SETTINGS"
grep -q 'LuoShuSmoothShape(24.dp)' "$SETTINGS"
grep -q 'heightIn(min = 64.dp)' "$SETTINGS"
grep -q 'Role.Switch' "$SETTINGS"
grep -q 'Switch(checked = checked, onCheckedChange = null' "$SETTINGS"
grep -q 'pageBackground = Color(LuoShuGlassPalette.LightBackground)' "$THEME"
grep -q 'internal fun LuoShuTopBar' "$COMPACT_LAYOUT"
grep -q 'internal fun LuoShuDetailBar' "$COMPACT_LAYOUT"
# Task errors can be expanded, and raw logs are filtered and composed lazily.
grep -q 'items(state.tasks' "$LOGS_MIUIX"
grep -q 'maxLines = if (expanded) Int.MAX_VALUE else 3' "$LOGS_MIUIX"
grep -q 'items(visibleLines' "$LOGS_MIUIX"
grep -q 'visibleLines.joinToString' "$LOGS_MIUIX"
grep -q 'logMatchesFilter' "$LOGS_MIUIX"
! grep -q 'padding(bottom = 96.dp)' "$LOGS_ROUTE"
! grep -q 'if (page == AppPage.Studio)' "$SHELL"

# Cross-page state, first-launch motion, and lazy loading are user-visible behavior.
JAVA_ROOT="$ROOT/android-app/app/src/main/java"
MOTION="$JAVA_ROOT/io/github/xgl34222220/luoshu/ui/theme/LuoShuMotion.kt"
! grep -R -E 'ScreenMaterial|ScreenCompact|UiStyle[.]MATERIAL' "$JAVA_ROOT"
grep -q 'rememberSaveableStateHolder()' "$SHELL"
grep -q 'Animatable(if (page == AppPage.Home && pageDirection == 0f) 1f else 0f)' "$SHELL"
grep -q 'viewModel.ensureMixConfig()' "$SHELL"
grep -q 'fun ensureMixConfig() = loadMixConfig(force = false)' "$JAVA_ROOT/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'rememberLazyListState()' "$MIUIX"
grep -q 'rememberLazyListState()' "$HOME_MIUIX"
grep -q 'rememberLazyListState()' "$STUDIO_MIUIX"
grep -q 'rememberSaveable' "$ROUTE"
grep -q 'selected = active, role = Role.Tab' "$MIUIX"
grep -q 'LuoShuSmoothShape(24.dp)' "$MIUIX"
grep -q 'defaultElevation = tokens.cardShadowElevation' "$MIUIX"
# Validate translucent light/dark roles and a low-cost elevation range instead
# of pinning the old decorative opacity and oversized bright-mode shadow.
python3 "$ROOT/scripts/glass_visual_hierarchy_test.py"
grep -q 'glassOutlineBrush = Brush.linearGradient' "$THEME"
for SCREEN in "$MIUIX" "$HOME_MIUIX" "$STUDIO_MIUIX" "$LOGS_MIUIX" "$SETTINGS"; do
    grep -q 'glassOutlineBrush' "$SCREEN"
    grep -q 'luoShuGlassHighlight' "$SCREEN"
done
grep -q 'AppBackdrop(appearance, dark)' "$SHELL"
grep -q 'LuoShuGlassBackdropDrawable(dark, pureBlack)' "$SHELL"
grep -q 'if (appearance.glassEnabled)' "$SHELL"
grep -q 'backdrop.draw(it.nativeCanvas)' "$SHELL"
grep -q 'val monetSupported = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S' "$SETTINGS"
grep -q 'val effectiveMonet = settings.monetEnabled && monetSupported' "$SETTINGS"
grep -q 'enabled = !effectiveMonet' "$SETTINGS"
grep -q 'enabled = monetSupported' "$SETTINGS"
grep -q 'pressedScale = .985f' "$MIUIX"
grep -q 'val progress = if (active && revealed)' "$MOTION"
grep -q 'rememberInfiniteTransition(label = "luoshuSkeleton")' "$MOTION"
grep -q 'else 0f' "$MOTION"

echo 'LuoShu MIUIx UI layout regression passed.'
