package io.github.xgl34222220.luoshu

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
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
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTheme

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
    AppPage.Logs,
)

@Composable
internal fun LuoShuAppShell(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    appearanceViewModel: AppearanceViewModel,
) {
    val appearance by appearanceViewModel.settings.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf(AppPage.Home) }
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
    BackHandler(enabled = page != AppPage.Home) { page = AppPage.Home }

    val homeActions = remember(viewModel, features) {
        HomeActions(
            refresh = {
                viewModel.refresh()
                features.refreshSystemWeight()
            },
            openFontLibrary = { page = AppPage.Library },
            openFontStudio = { page = AppPage.Studio },
            openLogs = { page = AppPage.Logs },
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
        val navigationBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
        val dockClearance = navigationBottom + when {
            !appearance.floatingDock -> 70.dp
            appearance.uiStyle == UiStyle.MIUIX && appearance.glassEnabled -> 34.dp
            else -> 84.dp
        }
        val contentModifier = Modifier
            .fillMaxSize()
            .then(if (blurActive) Modifier.hazeSource(state = hazeState) else Modifier)

        Box(Modifier.fillMaxSize()) {
            Box(modifier = contentModifier) {
                AppBackdrop(appearance, dark)
                AnimatedContent(
                    targetState = page,
                    modifier = Modifier.fillMaxSize(),
                    contentKey = { it },
                    transitionSpec = {
                        val direction = if (targetState.ordinal >= initialState.ordinal) 1 else -1
                        val enterDuration = if (appearance.uiStyle == UiStyle.MIUIX) 200 else 180
                        val exitDuration = if (appearance.uiStyle == UiStyle.MIUIX) 110 else 100
                        (fadeIn(tween(enterDuration)) + slideInHorizontally(tween(enterDuration)) { width ->
                            direction * width / 22
                        }).togetherWith(
                            fadeOut(tween(exitDuration)) + slideOutHorizontally(tween(exitDuration)) { width ->
                                -direction * width / 28
                            },
                        )
                    },
                    label = "luoshuPageTransition",
                ) { target ->
                    when (target) {
                        AppPage.Home -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            HomeRoute(
                                style = appearance.uiStyle,
                                state = viewModel.snapshot.toHomeUiState(features.systemWeight),
                                actions = homeActions,
                            )
                        }
                        AppPage.Library -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
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
                        AppPage.Studio -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            FontStudioRoute(
                                style = appearance.uiStyle,
                                state = viewModel.toFontStudioUiState(features),
                                actions = studioActions,
                            )
                        }
                        AppPage.Logs -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = dockClearance),
                        ) {
                            LogsRoute(
                                style = appearance.uiStyle,
                                state = viewModel.toLogsUiState(),
                                actions = logsActions,
                            )
                        }
                        AppPage.Settings -> AppearanceSettingsRoute(
                            settings = appearance,
                            actions = appearanceActions,
                        )
                    }
                }
            }

            if (page != AppPage.Settings) {
                if (appearance.uiStyle == UiStyle.MATERIAL) {
                    MaterialAppDock(
                        current = page,
                        onSelect = { page = it },
                        appearance = appearance,
                        hazeState = hazeState,
                        modifier = Modifier.align(Alignment.BottomCenter),
                    )
                } else {
                    MiuixAppDock(
                        current = page,
                        onSelect = { page = it },
                        appearance = appearance,
                        hazeState = hazeState,
                        modifier = Modifier.align(Alignment.BottomCenter),
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
                            listOf(
                                scheme.primary.copy(alpha = if (dark) .18f else .14f),
                                scheme.secondary.copy(alpha = if (dark) .09f else .07f),
                                Color.Transparent,
                            ),
                            center = Offset(size.width * .50f, size.height * 1.01f),
                            radius = size.width * .92f,
                        ),
                    )
                    drawRect(
                        Brush.radialGradient(
                            listOf(scheme.primary.copy(alpha = if (dark) .06f else .05f), Color.Transparent),
                            center = Offset(size.width * .92f, size.height * .08f),
                            radius = size.width * .58f,
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
        itemHeight = 52.dp,
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
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val floating = appearance.floatingDock
    val shape = if (floating) RoundedCornerShape(31.dp) else RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
    val activeGlass = appearance.glassEnabled
    val activeHaze = activeGlass && appearance.blurEnabled
    val hazeModifier = if (activeHaze) {
        Modifier.hazeEffect(state = hazeState, style = HazeMaterials.ultraThin()) {
            blurRadius = 30.dp
            noiseFactor = .025f
        }
    } else Modifier
    val glassBrush = when {
        activeGlass && dark -> Brush.verticalGradient(
            listOf(
                Color.White.copy(alpha = .10f),
                tokens.elevatedCardBackground.copy(alpha = .08f),
                scheme.primary.copy(alpha = .05f),
            ),
        )
        activeGlass -> Brush.verticalGradient(
            listOf(
                Color.White.copy(alpha = .30f),
                Color.White.copy(alpha = .10f),
                scheme.primary.copy(alpha = .055f),
            ),
        )
        else -> Brush.verticalGradient(
            listOf(tokens.elevatedCardBackground.copy(alpha = .98f), tokens.elevatedCardBackground.copy(alpha = .98f)),
        )
    }

    AppDockLayout(
        pages = dockPages,
        current = current,
        onSelect = onSelect,
        itemHeight = 52.dp,
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 12.dp).padding(bottom = bottomInset + 8.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) if (activeGlass) 14.dp else 12.dp else 5.dp, shape, clip = false)
            .clip(shape)
            .then(hazeModifier)
            .background(glassBrush)
            .drawBehind {
                if (activeGlass) {
                    val radius = 31.dp.toPx()
                    val corners = CornerRadius(radius, radius)
                    drawRoundRect(
                        brush = Brush.radialGradient(
                            colors = listOf(
                                Color.White.copy(alpha = if (dark) .18f else .46f),
                                Color.White.copy(alpha = if (dark) .06f else .14f),
                                Color.Transparent,
                            ),
                            center = Offset(size.width * .23f, 0f),
                            radius = size.width * .62f,
                        ),
                        cornerRadius = corners,
                    )
                    drawRoundRect(
                        brush = Brush.radialGradient(
                            colors = listOf(
                                scheme.primary.copy(alpha = if (dark) .11f else .085f),
                                scheme.secondary.copy(alpha = if (dark) .045f else .035f),
                                Color.Transparent,
                            ),
                            center = Offset(size.width * .76f, size.height * 1.18f),
                            radius = size.width * .58f,
                        ),
                        cornerRadius = corners,
                    )
                    drawRoundRect(
                        brush = Brush.linearGradient(
                            colors = listOf(
                                Color.White.copy(alpha = if (dark) .28f else .72f),
                                Color.White.copy(alpha = if (dark) .08f else .18f),
                                scheme.primary.copy(alpha = if (dark) .14f else .11f),
                                Color.Transparent,
                            ),
                            start = Offset.Zero,
                            end = Offset(size.width, size.height),
                        ),
                        cornerRadius = corners,
                        style = Stroke(width = 1.05.dp.toPx()),
                    )
                    drawLine(
                        color = Color.White.copy(alpha = if (dark) .20f else .52f),
                        start = Offset(radius * .78f, 1.25.dp.toPx()),
                        end = Offset(size.width - radius * .78f, 1.25.dp.toPx()),
                        strokeWidth = .8.dp.toPx(),
                    )
                }
            }
            .border(
                if (activeGlass) .6.dp else 1.dp,
                if (activeGlass) {
                    if (dark) Color.White.copy(alpha = .14f) else Color.White.copy(alpha = .42f)
                } else if (dark) Color.White.copy(alpha = .10f) else Color.White.copy(alpha = .58f),
                shape,
            )
            .padding(start = 5.dp, top = 5.dp, end = 5.dp, bottom = if (floating) 5.dp else bottomInset + 5.dp),
        indicatorColor = if (activeGlass) {
            Color.White.copy(alpha = if (dark) .08f else .18f)
        } else {
            scheme.primary.copy(alpha = if (dark) .20f else .12f)
        },
        indicatorBorderColor = if (activeGlass) {
            if (dark) Color.White.copy(alpha = .20f) else Color.White.copy(alpha = .48f)
        } else {
            Color.Transparent
        },
        indicatorShadow = 0.dp,
        selectedColor = scheme.primary,
        unselectedColor = scheme.onSurfaceVariant.copy(alpha = .80f),
        label = "luoshuMiuixDockIndicator",
        liquidLens = activeGlass,
    )
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
    liquidLens: Boolean = false,
) {
    BoxWithConstraints(modifier = modifier) {
        val itemWidth = maxWidth / pages.size.toFloat()
        val targetIndex = pages.indexOf(current).coerceAtLeast(0)
        val indicatorInset = if (liquidLens) 5.dp else 7.dp
        val indicatorX by animateDpAsState(
            targetValue = itemWidth * targetIndex.toFloat(),
            animationSpec = spring(
                dampingRatio = if (liquidLens) .64f else .76f,
                stiffness = if (liquidLens) Spring.StiffnessLow else Spring.StiffnessMediumLow,
            ),
            label = label,
        )
        val indicatorShape = RoundedCornerShape(if (liquidLens) 20.dp else 18.dp)
        Box(
            modifier = Modifier
                .offset(x = indicatorX + indicatorInset)
                .width(itemWidth - (indicatorInset * 2))
                .height(itemHeight)
                .shadow(indicatorShadow, indicatorShape, clip = false)
                .clip(indicatorShape)
                .background(indicatorColor)
                .drawBehind {
                    if (liquidLens) {
                        val radius = 20.dp.toPx()
                        val corners = CornerRadius(radius, radius)
                        drawRoundRect(
                            brush = Brush.radialGradient(
                                colors = listOf(
                                    Color.White.copy(alpha = .30f),
                                    Color.White.copy(alpha = .08f),
                                    Color.Transparent,
                                ),
                                center = Offset(size.width * .28f, size.height * .08f),
                                radius = size.width * .58f,
                            ),
                            cornerRadius = corners,
                        )
                        drawRoundRect(
                            brush = Brush.radialGradient(
                                colors = listOf(selectedColor.copy(alpha = .15f), Color.Transparent),
                                center = Offset(size.width * .72f, size.height * 1.08f),
                                radius = size.width * .56f,
                            ),
                            cornerRadius = corners,
                        )
                        drawLine(
                            color = Color.White.copy(alpha = .32f),
                            start = Offset(radius * .62f, 1.dp.toPx()),
                            end = Offset(size.width - radius * .62f, 1.dp.toPx()),
                            strokeWidth = .7.dp.toPx(),
                        )
                    }
                }
                .border(if (liquidLens) .7.dp else 1.dp, indicatorBorderColor, indicatorShape),
        )
        Row(Modifier.fillMaxWidth()) {
            pages.forEach { page ->
                val selected = current == page
                val interactionSource = remember(page) { MutableInteractionSource() }
                val pressed by interactionSource.collectIsPressedAsState()
                val baseItemColor = if (selected) selectedColor else unselectedColor
                val itemColor = if (pressed) baseItemColor.copy(alpha = .62f) else baseItemColor
                Column(
                    modifier = Modifier
                        .width(itemWidth)
                        .height(itemHeight)
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
