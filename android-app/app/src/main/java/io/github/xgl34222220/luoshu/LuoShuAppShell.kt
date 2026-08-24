package io.github.xgl34222220.luoshu

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.chrisbanes.haze.HazeState
import dev.chrisbanes.haze.hazeEffect
import dev.chrisbanes.haze.hazeSource
import dev.chrisbanes.haze.materials.ExperimentalHazeMaterialsApi
import dev.chrisbanes.haze.materials.HazeMaterials
import dev.chrisbanes.haze.rememberHazeState
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.dialogs.FontActionDialogRoute
import io.github.xgl34222220.luoshu.ui.dialogs.FontActionKind
import io.github.xgl34222220.luoshu.ui.dialogs.FontPickerDialogRoute
import io.github.xgl34222220.luoshu.ui.font.fontNormalizedWeight
import io.github.xgl34222220.luoshu.ui.font.selectedFontId
import io.github.xgl34222220.luoshu.ui.glass.liquidGlassLens
import io.github.xgl34222220.luoshu.ui.home.HomeActions
import io.github.xgl34222220.luoshu.ui.home.HomeRoute
import io.github.xgl34222220.luoshu.ui.home.toHomeUiState
import io.github.xgl34222220.luoshu.ui.library.FontLibraryActions
import io.github.xgl34222220.luoshu.ui.library.FontLibraryRoute
import io.github.xgl34222220.luoshu.ui.library.toFontLibraryUiState
import io.github.xgl34222220.luoshu.ui.logs.LogsActions
import io.github.xgl34222220.luoshu.ui.logs.LogsRoute
import io.github.xgl34222220.luoshu.ui.logs.toLogsUiState
import io.github.xgl34222220.luoshu.ui.settings.AppearanceActions
import io.github.xgl34222220.luoshu.ui.settings.AppearanceSettingsRoute
import io.github.xgl34222220.luoshu.ui.studio.FontStudioActions
import io.github.xgl34222220.luoshu.ui.studio.FontStudioRoute
import io.github.xgl34222220.luoshu.ui.studio.toFontStudioUiState
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTheme
import top.yukonga.miuix.kmp.blur.LayerBackdrop
import top.yukonga.miuix.kmp.blur.blur
import top.yukonga.miuix.kmp.blur.colorControls
import top.yukonga.miuix.kmp.blur.drawBackdrop
import top.yukonga.miuix.kmp.blur.highlight.Highlight
import top.yukonga.miuix.kmp.blur.isRuntimeShaderSupported
import top.yukonga.miuix.kmp.blur.layerBackdrop
import top.yukonga.miuix.kmp.blur.rememberLayerBackdrop
import top.yukonga.miuix.kmp.squircle.squircleClip

internal enum class AppPage(
    val label: String,
    val icon: ImageVector,
    val dockOpticalScale: Float = 1f,
) {
    Home("首页", Icons.Rounded.Home, .94f),
    Library("字体库", Icons.Rounded.ListAlt, 1.00f),
    Studio("组合", Icons.Rounded.Layers, .96f),
    Logs("任务", Icons.Rounded.Description, .96f),
    Settings("设置", Icons.Rounded.Settings, .94f),
}

private val dockPages = listOf(
    AppPage.Home,
    AppPage.Library,
    AppPage.Studio,
    AppPage.Settings,
)

@Composable
internal fun LuoShuAppShell(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    appearanceViewModel: AppearanceViewModel,
) {
    val appearance by appearanceViewModel.settings.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf(AppPage.Home) }
    var settingsDetailVisible by rememberSaveable { mutableStateOf(false) }
    var logsReturnPage by rememberSaveable { mutableStateOf(AppPage.Home) }
    var pendingApply by remember { mutableStateOf<FontItem?>(null) }
    var pendingDelete by remember { mutableStateOf<FontItem?>(null) }
    var restoreDefault by remember { mutableStateOf(false) }
    var pickerSlot by remember { mutableStateOf<MixSlot?>(null) }

    LaunchedEffect(Unit) {
        viewModel.refresh()
        features.refreshSystemWeight()
    }
    LaunchedEffect(page) {
        when (page) {
            AppPage.Home -> features.refreshSystemWeight()
            AppPage.Library -> viewModel.ensureFonts()
            AppPage.Studio -> {
                viewModel.ensureFonts()
                viewModel.refreshMixConfig()
            }
            AppPage.Logs -> viewModel.refreshLogs()
            AppPage.Settings -> Unit
        }
    }
    LaunchedEffect(page) {
        if (page != AppPage.Settings) settingsDetailVisible = false
    }
    BackHandler(
        enabled = page != AppPage.Home && !(page == AppPage.Settings && settingsDetailVisible),
    ) { page = if (page == AppPage.Logs) logsReturnPage else AppPage.Home }

    val homeActions = remember(viewModel, features) {
        HomeActions(
            refresh = {
                viewModel.refresh()
                features.refreshSystemWeight()
            },
            openFontLibrary = { page = AppPage.Library },
            openFontStudio = { page = AppPage.Studio },
            openLogs = {
                logsReturnPage = AppPage.Home
                page = AppPage.Logs
            },
            openSettings = { page = AppPage.Settings },
            restoreDefault = { restoreDefault = true },
            reboot = viewModel::rebootDevice,
            previewSystemWeight = features::previewSystemWeight,
            resetSystemWeight = features::resetSystemWeight,
        )
    }
    val libraryActions = remember(viewModel) {
        FontLibraryActions(
            refresh = { viewModel.refreshFonts(force = true) },
            setQuery = viewModel::setSearchQuery,
            apply = { pendingApply = it },
            delete = { pendingDelete = it },
            restoreDefault = { restoreDefault = true },
        )
    }
    val studioActions = remember(viewModel, features) {
        FontStudioActions(
            refresh = viewModel::refreshMixConfig,
            pickSlot = { pickerSlot = it },
            updateWeight = viewModel::updateMixWeight,
            updateAxis = viewModel::updateMixAxis,
            inspectCoverage = features::inspectCoverage,
            startMix = viewModel::startMix,
            applyDirect = viewModel::applyFont,
        )
    }
    val logsActions = remember(viewModel) { LogsActions(refresh = viewModel::refreshLogs) }
    val appearanceActions = remember(appearanceViewModel) {
        AppearanceActions(
            setUiStyle = appearanceViewModel::setUiStyle,
            setThemeMode = appearanceViewModel::setThemeMode,
            setSeedArgb = appearanceViewModel::setSeedArgb,
            setKolorStyle = appearanceViewModel::setKolorStyle,
            setMonetEnabled = appearanceViewModel::setMonetEnabled,
            setAmoledBlack = appearanceViewModel::setAmoledBlack,
            setBlurEnabled = appearanceViewModel::setBlurEnabled,
            setGlassEnabled = appearanceViewModel::setGlassEnabled,
            setFloatingDock = appearanceViewModel::setFloatingDock,
            setHighRefreshRate = appearanceViewModel::setHighRefreshRate,
        )
    }
    val validFonts = remember(viewModel.fonts) { viewModel.fonts.filter { it.valid } }

    LuoShuTheme(appearance) {
        val dark = MaterialTheme.colorScheme.background.luminance() < .5f
        val blurActive = appearance.blurEnabled && appearance.glassEnabled
        val hazeState = rememberHazeState(blurEnabled = blurActive)
        val liquidBackdrop = rememberLayerBackdrop()
        val liquidGlassSupported = blurActive &&
            appearance.uiStyle == UiStyle.MIUIX &&
            isRuntimeShaderSupported()
        val navigationBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
        val showDock = page != AppPage.Logs && !(page == AppPage.Settings && settingsDetailVisible)
        val edgeToEdgeGlass = appearance.uiStyle == UiStyle.MIUIX &&
            appearance.glassEnabled && appearance.floatingDock && showDock
        // A floating glass dock overlays a full-height viewport. Lists own the trailing
        // safe space so content can pass behind the glass yet still scroll fully clear.
        val dockClearance = when {
            !showDock -> 0.dp
            edgeToEdgeGlass -> 0.dp
            !appearance.floatingDock -> navigationBottom + 70.dp
            else -> navigationBottom + 76.dp
        }
        val dockContentPadding = if (edgeToEdgeGlass) navigationBottom + 78.dp else 0.dp
        val contentModifier = Modifier
            .fillMaxSize()
            .then(if (blurActive && !liquidGlassSupported) Modifier.hazeSource(state = hazeState) else Modifier)
            .then(if (liquidGlassSupported) Modifier.layerBackdrop(liquidBackdrop) else Modifier)

        Box(Modifier.fillMaxSize()) {
            Box(modifier = contentModifier) {
                AppBackdrop(appearance, dark)
                AnimatedContent(
                    targetState = page,
                    modifier = Modifier.fillMaxSize(),
                    contentKey = { it },
                    transitionSpec = {
                        when {
                            targetState == AppPage.Logs -> {
                                (fadeIn(tween(260)) + slideInHorizontally(tween(340, easing = FastOutSlowInEasing)) { it })
                                    .togetherWith(
                                        fadeOut(tween(220), targetAlpha = .52f) +
                                            slideOutHorizontally(tween(340, easing = FastOutSlowInEasing)) { -it / 7 },
                                    )
                            }
                            initialState == AppPage.Logs -> {
                                (fadeIn(tween(240)) + slideInHorizontally(tween(340, easing = FastOutSlowInEasing)) { -it / 7 })
                                    .togetherWith(
                                        fadeOut(tween(220)) +
                                            slideOutHorizontally(tween(340, easing = FastOutSlowInEasing)) { it },
                                    )
                            }
                            else -> {
                                val direction = if (targetState.ordinal >= initialState.ordinal) 1 else -1
                                (fadeIn(tween(260)) +
                                    slideInHorizontally(tween(360, easing = FastOutSlowInEasing)) { direction * it * 3 / 4 })
                                    .togetherWith(
                                        fadeOut(tween(210), targetAlpha = .42f) +
                                            slideOutHorizontally(tween(360, easing = FastOutSlowInEasing)) { -direction * it * 3 / 5 },
                                    )
                            }
                        }
                    },
                    label = "luoshuPageTransition",
                ) { target ->
                    when (target) {
                        AppPage.Home -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            CompositionLocalProvider(LocalDockContentPadding provides dockContentPadding) {
                                HomeRoute(
                                    style = appearance.uiStyle,
                                    state = viewModel.snapshot.toHomeUiState(features.systemWeight),
                                    actions = homeActions,
                                )
                            }
                        }
                        AppPage.Library -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            CompositionLocalProvider(LocalDockContentPadding provides dockContentPadding) {
                                FontLibraryRoute(
                                    style = appearance.uiStyle,
                                    state = viewModel.toFontLibraryUiState(),
                                    actions = libraryActions,
                                    topActions = {
                                        NativeImportOverlay(
                                            viewModel = viewModel,
                                            style = appearance.uiStyle,
                                            modifier = Modifier.fillMaxWidth(),
                                            embedded = true,
                                        )
                                    },
                                )
                            }
                        }
                        AppPage.Studio -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            CompositionLocalProvider(LocalDockContentPadding provides dockContentPadding) {
                                FontStudioRoute(
                                    style = appearance.uiStyle,
                                    state = viewModel.toFontStudioUiState(features),
                                    actions = studioActions,
                                )
                            }
                        }
                        AppPage.Logs -> {
                            val detailShape = RoundedCornerShape(topStart = 32.dp, bottomStart = 32.dp)
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(start = if (appearance.uiStyle == UiStyle.MIUIX) 6.dp else 0.dp)
                                    .then(
                                        if (appearance.uiStyle == UiStyle.MIUIX) {
                                            Modifier
                                                .shadow(22.dp, detailShape, clip = false)
                                                .clip(detailShape)
                                                .background(LocalMiuixTokens.current.pageBackground)
                                        } else {
                                            Modifier
                                        },
                                    )
                                    .padding(bottom = dockClearance),
                            ) {
                                CompositionLocalProvider(LocalDockContentPadding provides dockContentPadding) {
                                    LogsRoute(
                                        style = appearance.uiStyle,
                                        state = viewModel.toLogsUiState(),
                                        actions = logsActions,
                                        onBack = { page = logsReturnPage },
                                    )
                                }
                            }
                        }
                        AppPage.Settings -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            CompositionLocalProvider(LocalDockContentPadding provides dockContentPadding) {
                                AppearanceSettingsRoute(
                                    settings = appearance,
                                    actions = appearanceActions,
                                    onOpenTasks = {
                                        logsReturnPage = AppPage.Settings
                                        page = AppPage.Logs
                                    },
                                    onDetailChanged = { settingsDetailVisible = it },
                                )
                            }
                        }
                    }
                }
            }

            val dockPage = if (page in dockPages) page else logsReturnPage
            AnimatedVisibility(
                visible = showDock,
                modifier = Modifier.align(Alignment.BottomCenter),
                enter = fadeIn(tween(220)) + slideInVertically(tween(300, easing = FastOutSlowInEasing)) { it / 2 },
                exit = fadeOut(tween(170)) + slideOutVertically(tween(240, easing = FastOutSlowInEasing)) { it / 2 },
            ) {
                if (appearance.uiStyle == UiStyle.MATERIAL) {
                    MaterialAppDock(
                        current = dockPage,
                        onSelect = { page = it },
                        appearance = appearance,
                        hazeState = hazeState,
                    )
                } else {
                    MiuixAppDock(
                        current = dockPage,
                        onSelect = { page = it },
                        appearance = appearance,
                        hazeState = hazeState,
                        backdrop = liquidBackdrop.takeIf { liquidGlassSupported },
                    )
                }
            }

        }

        pendingApply?.let { font ->
            FontActionDialogRoute(
                style = appearance.uiStyle,
                kind = FontActionKind.APPLY,
                message = if (font.supportsCjk) {
                    "直接应用「${font.name}」。准备完成后需要完整重启手机。"
                } else {
                    "「${font.name}」不包含完整中文字形。直接应用后中文会继续使用系统默认字体，看起来可能没有变化；建议在组合页把它作为英文字体使用。"
                },
                onDismiss = { pendingApply = null },
                onConfirm = {
                    pendingApply = null
                    viewModel.applyFont(font.id)
                },
            )
        }

        pendingDelete?.let { font ->
            FontActionDialogRoute(
                style = appearance.uiStyle,
                kind = FontActionKind.DELETE,
                message = "确定删除「${font.name}」吗？字体文件和相关缓存将一并移除。",
                onDismiss = { pendingDelete = null },
                onConfirm = {
                    pendingDelete = null
                    viewModel.deleteFont(font.id)
                },
            )
        }

        if (restoreDefault) {
            FontActionDialogRoute(
                style = appearance.uiStyle,
                kind = FontActionKind.RESTORE,
                message = "恢复 ROM 自带字体映射。完成后需要完整重启手机。",
                onDismiss = { restoreDefault = false },
                onConfirm = {
                    restoreDefault = false
                    viewModel.applyFont("default")
                },
            )
        }

        pickerSlot?.let { slot ->
            FontPickerDialogRoute(
                style = appearance.uiStyle,
                slot = slot,
                fonts = validFonts,
                selected = selectedFontId(viewModel.mixState, slot),
                onDismiss = { pickerSlot = null },
                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(
                        slot,
                        fontNormalizedWeight(
                            font,
                            when (slot) {
                                MixSlot.Cjk -> viewModel.mixState.cjkWeight
                                MixSlot.Latin -> viewModel.mixState.latinWeight
                                MixSlot.Digit -> viewModel.mixState.digitWeight
                            },
                        ),
                    )
                    pickerSlot = null
                },
            )
        }
    }
}

@Composable
private fun AppBackdrop(appearance: AppearanceSettings, dark: Boolean) {
    val scheme = MaterialTheme.colorScheme
    val miuix = appearance.uiStyle == UiStyle.MIUIX
    val base = when {
        miuix -> listOf(LocalMiuixTokens.current.pageBackground, LocalMiuixTokens.current.pageBackground)
        dark -> listOf(scheme.background, scheme.surfaceContainerLow, scheme.background)
        else -> listOf(scheme.background, scheme.surfaceContainerLowest, scheme.background)
    }
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(base))
            .drawBehind {
                if (miuix) {
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.primary.copy(alpha = if (dark) .09f else .10f), Color.Transparent),
                            center = Offset(size.width * .92f, size.height * .02f),
                            radius = size.width * .85f,
                        ),
                    )
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.secondary.copy(alpha = if (dark) .06f else .07f), Color.Transparent),
                            center = Offset(size.width * .04f, size.height * .82f),
                            radius = size.width,
                        ),
                    )
                } else {
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.secondary.copy(alpha = if (dark) .13f else .20f), Color.Transparent),
                            center = Offset(size.width * .9f, size.height * .06f),
                            radius = size.width * .72f,
                        ),
                    )
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.primary.copy(alpha = if (dark) .10f else .16f), Color.Transparent),
                            center = Offset(size.width * .02f, size.height * .54f),
                            radius = size.width * .82f,
                        ),
                    )
                }
            },
    )
}

@OptIn(ExperimentalHazeMaterialsApi::class)
@Composable
private fun MaterialAppDock(
    current: AppPage,
    onSelect: (AppPage) -> Unit,
    appearance: AppearanceSettings,
    hazeState: HazeState,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val floating = appearance.floatingDock
    val shape = if (floating) RoundedCornerShape(26.dp) else RoundedCornerShape(topStart = 26.dp, topEnd = 26.dp)
    val activeHaze = appearance.blurEnabled && appearance.glassEnabled
    val hazeModifier = if (activeHaze) {
        Modifier.hazeEffect(state = hazeState, style = HazeMaterials.ultraThin()) {
            blurRadius = 26.dp
            noiseFactor = .04f
        }
    } else Modifier

    AppDockLayout(
        pages = dockPages,
        current = current,
        onSelect = onSelect,
        itemHeight = 48.dp,
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 16.dp).padding(bottom = bottomInset + 10.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) 14.dp else 6.dp, shape, clip = false)
            .clip(shape)
            .then(hazeModifier)
            .background(
                when {
                    activeHaze && dark -> scheme.surface.copy(alpha = .34f)
                    activeHaze -> Color.White.copy(alpha = .28f)
                    else -> scheme.surface.copy(alpha = .98f)
                },
            )
            .border(1.dp, if (dark) Color.White.copy(alpha = .12f) else Color.White.copy(alpha = .72f), shape)
            .padding(start = 6.dp, top = 6.dp, end = 6.dp, bottom = if (floating) 6.dp else bottomInset + 6.dp),
        indicatorColor = scheme.primaryContainer.copy(alpha = .64f),
        selectedColor = scheme.primary,
        unselectedColor = scheme.onSurfaceVariant,
        label = "luoshuMaterialDockIndicator",
    )
}

@OptIn(ExperimentalHazeMaterialsApi::class)
@Composable
private fun MiuixAppDock(
    current: AppPage,
    onSelect: (AppPage) -> Unit,
    appearance: AppearanceSettings,
    hazeState: HazeState,
    backdrop: LayerBackdrop?,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val floating = appearance.floatingDock
    val shape = if (floating) RoundedCornerShape(24.dp) else RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
    val activeGlass = appearance.glassEnabled
    val runtimeLiquid = activeGlass && appearance.blurEnabled && backdrop != null && isRuntimeShaderSupported()
    val activeHaze = activeGlass && appearance.blurEnabled && !runtimeLiquid
    val dockSurfaceBackdrop = rememberLayerBackdrop()
    val hazeModifier = if (activeHaze) {
        Modifier.hazeEffect(state = hazeState, style = HazeMaterials.ultraThin()) {
            blurRadius = 24.dp
            noiseFactor = .012f
        }
    } else Modifier
    val glassBrush = when {
        activeGlass && dark -> Brush.verticalGradient(listOf(Color.White.copy(alpha = .10f), Color.White.copy(alpha = .035f)))
        activeGlass -> Brush.verticalGradient(listOf(Color.White.copy(alpha = .22f), Color.White.copy(alpha = .09f)))
        else -> Brush.verticalGradient(
            listOf(tokens.elevatedCardBackground.copy(alpha = .98f), tokens.elevatedCardBackground.copy(alpha = .98f)),
        )
    }
    val shellTint = when {
        dark -> scheme.surface.copy(alpha = .42f)
        else -> Color.White.copy(alpha = .46f)
    }
    val liquidShellModifier = if (runtimeLiquid) {
        Modifier.drawBackdrop(
            backdrop = requireNotNull(backdrop),
            shape = { shape },
            effects = {
                padding = maxOf(padding, 24.dp.toPx())
                colorControls(
                    brightness = if (dark) -.015f else .025f,
                    contrast = 1.035f,
                    saturation = 1.34f,
                )
                blur(7.dp.toPx(), 7.dp.toPx())
                liquidGlassLens(
                    refractionHeight = 14.dp.toPx(),
                    refractionAmount = 10.dp.toPx(),
                    chromaticAberration = .035f,
                )
            },
            highlight = {
                (if (dark) Highlight.GlassStrokeSmallDark else Highlight.GlassStrokeSmallLight)
                    .copy(alpha = if (dark) .72f else .86f)
            },
            onDrawSurface = {
                drawRect(shellTint)
                drawRect(
                    brush = Brush.radialGradient(
                        colors = listOf(
                            Color.White.copy(alpha = if (dark) .06f else .20f),
                            Color.Transparent,
                        ),
                        center = Offset(size.width * .16f, 0f),
                        radius = size.width * .70f,
                    ),
                )
            },
        )
    } else {
        Modifier
            .then(hazeModifier)
            .background(glassBrush)
            .drawBehind {
                if (activeGlass) {
                    drawRoundRect(
                        brush = Brush.radialGradient(
                            colors = listOf(
                                Color.White.copy(alpha = if (dark) .08f else .24f),
                                Color.Transparent,
                            ),
                            center = Offset(size.width * .18f, 0f),
                            radius = size.width * .72f,
                        ),
                        cornerRadius = CornerRadius(size.height / 2f),
                    )
                }
            }
    }

    // Three independent layers mirror the reference implementation: page backdrop -> refractive
    // shell -> moving refractive lens. Icons and labels are siblings above all shader layers, so an
    // OEM compositor can never turn their offscreen buffers into the old white rectangles.
    Box(
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 14.dp).padding(bottom = bottomInset + 9.dp) else Modifier)
            .fillMaxWidth()
            .height(52.dp + if (floating) 0.dp else bottomInset),
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .shadow(if (floating) 10.dp else 3.dp, shape, clip = false)
                .squircleClip(24.dp)
                .then(if (runtimeLiquid) Modifier.layerBackdrop(dockSurfaceBackdrop) else Modifier)
                .then(liquidShellModifier)
                .border(
                    if (runtimeLiquid) .45.dp else .7.dp,
                    if (activeGlass) {
                        if (dark) Color.White.copy(alpha = .11f) else Color.White.copy(alpha = .32f)
                    } else if (dark) Color.White.copy(alpha = .10f) else Color.White.copy(alpha = .50f),
                    shape,
                ),
        )

        AppDockLayout(
            pages = dockPages,
            current = current,
            onSelect = onSelect,
            itemHeight = 44.dp,
            modifier = Modifier
                .fillMaxSize()
                .padding(start = 4.dp, top = 4.dp, end = 4.dp, bottom = if (floating) 4.dp else bottomInset + 4.dp),
            indicatorColor = scheme.primary.copy(alpha = if (dark) .25f else .13f),
            indicatorBorderColor = Color.White.copy(alpha = if (dark) .13f else .34f),
            indicatorShadow = 0.dp,
            selectedColor = scheme.primary,
            unselectedColor = scheme.onSurfaceVariant.copy(alpha = .72f),
            label = "luoshuMiuixDockIndicator",
            liquidGlass = activeGlass,
            indicatorBackdrop = dockSurfaceBackdrop.takeIf { runtimeLiquid },
            dark = dark,
        )
    }
}

@Composable
private fun AppDockLayout(
    pages: List<AppPage>,
    current: AppPage,
    onSelect: (AppPage) -> Unit,
    itemHeight: androidx.compose.ui.unit.Dp,
    modifier: Modifier,
    indicatorColor: Color,
    indicatorBorderColor: Color = Color.Transparent,
    indicatorShadow: androidx.compose.ui.unit.Dp = 0.dp,
    selectedColor: Color,
    unselectedColor: Color,
    label: String,
    liquidGlass: Boolean = false,
    indicatorBackdrop: LayerBackdrop? = null,
    dark: Boolean = false,
) {
    BoxWithConstraints(modifier = modifier) {
        val itemWidth = maxWidth / pages.size.toFloat()
        val targetIndex = pages.indexOf(current).coerceAtLeast(0)
        val indicatorInset = 5.dp
        val liquidStretch = remember { Animatable(0f) }
        var travelDirection by remember { mutableFloatStateOf(0f) }
        var previousIndex by remember { mutableStateOf(targetIndex) }
        LaunchedEffect(targetIndex) {
            if (targetIndex != previousIndex) {
                travelDirection = if (targetIndex > previousIndex) 1f else -1f
                previousIndex = targetIndex
                liquidStretch.snapTo(1f)
                liquidStretch.animateTo(
                    targetValue = 0f,
                    animationSpec = spring(
                        dampingRatio = .55f,
                        stiffness = Spring.StiffnessMediumLow,
                    ),
                )
            }
        }
        val indicatorX by animateDpAsState(
            targetValue = itemWidth * targetIndex.toFloat(),
            animationSpec = spring(
                dampingRatio = if (liquidGlass) .68f else .84f,
                stiffness = if (liquidGlass) 310f else Spring.StiffnessMediumLow,
            ),
            label = label,
        )
        val liquidExtra = if (liquidGlass) 10.dp * liquidStretch.value else 0.dp
        val indicatorStart = indicatorX + indicatorInset - if (travelDirection < 0f) liquidExtra else 0.dp
        val indicatorShape = RoundedCornerShape(18.dp)
        val activeLens = liquidGlass && indicatorBackdrop != null
        val movingLensModifier = if (activeLens) {
            Modifier.drawBackdrop(
                backdrop = requireNotNull(indicatorBackdrop),
                shape = { indicatorShape },
                effects = {
                    val stretch = liquidStretch.value
                    padding = maxOf(padding, 18.dp.toPx())
                    colorControls(contrast = 1.04f, saturation = 1.28f)
                    blur(2.25.dp.toPx(), 2.25.dp.toPx())
                    liquidGlassLens(
                        refractionHeight = (10.dp + 3.dp * stretch).toPx(),
                        refractionAmount = (11.dp + 4.dp * stretch).toPx(),
                        depthEffect = true,
                        chromaticAberration = .08f + .10f * stretch,
                    )
                },
                highlight = {
                    (if (dark) Highlight.GlassStrokeSmallDark else Highlight.GlassStrokeSmallLight)
                        .copy(alpha = .88f)
                },
                layerBlock = {
                    scaleY = 1f - .045f * liquidStretch.value
                },
                onDrawSurface = {
                    drawRect(indicatorColor)
                    drawRect(
                        brush = Brush.linearGradient(
                            colors = listOf(
                                Color.White.copy(alpha = if (dark) .055f else .16f),
                                Color.Transparent,
                            ),
                        ),
                    )
                },
            )
        } else {
            Modifier
                .drawBehind {
                    val radius = CornerRadius(size.height / 2f)
                    drawRoundRect(
                        brush = Brush.verticalGradient(
                            if (liquidGlass) {
                                listOf(
                                    indicatorColor.copy(alpha = (indicatorColor.alpha * 1.18f).coerceAtMost(1f)),
                                    indicatorColor.copy(alpha = indicatorColor.alpha * .72f),
                                )
                            } else {
                                listOf(indicatorColor, indicatorColor)
                            },
                        ),
                        cornerRadius = radius,
                    )
                    if (liquidGlass) {
                        drawRoundRect(
                            brush = Brush.radialGradient(
                                colors = listOf(
                                    Color.White.copy(alpha = if (dark) .10f else .24f),
                                    Color.Transparent,
                                ),
                                center = Offset(size.width * .27f, 0f),
                                radius = size.width * .74f,
                            ),
                            cornerRadius = radius,
                        )
                    }
                }
        }
        Box(
            modifier = Modifier
                .offset(x = indicatorStart)
                .width(itemWidth - (indicatorInset * 2) + liquidExtra)
                .height(itemHeight)
                .shadow(if (activeLens) 2.dp else indicatorShadow, indicatorShape, clip = false)
                .squircleClip(18.dp)
                .then(movingLensModifier)
                .border(1.dp, indicatorBorderColor, indicatorShape),
        )
        Row(Modifier.fillMaxWidth()) {
            pages.forEach { page ->
                val selected = current == page
                val interactionSource = remember(page) { MutableInteractionSource() }
                val pressed by interactionSource.collectIsPressedAsState()
                val baseItemColor = if (selected) selectedColor else unselectedColor
                val itemColor by animateColorAsState(
                    targetValue = if (pressed) baseItemColor.copy(alpha = .62f) else baseItemColor,
                    animationSpec = tween(170),
                    label = "${page.name}DockColor",
                )
                val itemScale by animateFloatAsState(
                    targetValue = when {
                        pressed -> .92f
                        selected && liquidGlass -> 1.035f
                        else -> 1f
                    },
                    animationSpec = spring(dampingRatio = .66f, stiffness = 520f),
                    label = "${page.name}DockScale",
                )
                Column(
                    modifier = Modifier
                        .width(itemWidth)
                        .height(itemHeight)
                        .graphicsLayer {
                            scaleX = itemScale
                            scaleY = itemScale
                        }
                        .clip(RoundedCornerShape(18.dp))
                        .clickable(
                            interactionSource = interactionSource,
                            indication = null,
                        ) { onSelect(page) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    LuoShuGlyph(
                        imageVector = page.icon,
                        contentDescription = page.label,
                        size = LuoShuIconTokens.DockGlyph,
                        opticalScale = page.dockOpticalScale,
                        tint = itemColor,
                    )
                    Spacer(Modifier.height(1.dp))
                    Text(
                        page.label,
                        color = itemColor,
                        fontSize = 10.sp,
                        fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}
