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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
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
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTheme

internal enum class AppPage(val label: String, val icon: ImageVector) {
    Home("首页", Icons.Rounded.Home),
    Library("字体库", Icons.Rounded.ListAlt),
    Studio("组合", Icons.Rounded.Layers),
    Logs("任务", Icons.Rounded.Description),
    Settings("设置", Icons.Rounded.Settings),
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
        )
    }
    val validFonts = remember(viewModel.fonts) { viewModel.fonts.filter { it.valid } }

    LuoShuTheme(appearance) {
        val dark = MaterialTheme.colorScheme.background.luminance() < .5f
        val blurActive = appearance.blurEnabled && appearance.glassEnabled
        val hazeState = rememberHazeState(blurEnabled = blurActive)
        val navigationBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
        val libraryDockClearance = navigationBottom + if (appearance.floatingDock) 84.dp else 68.dp
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
                        val enterDuration = if (appearance.uiStyle == UiStyle.MIUIX) 250 else 220
                        val exitDuration = if (appearance.uiStyle == UiStyle.MIUIX) 180 else 160
                        (fadeIn(tween(enterDuration)) + slideInHorizontally(tween(enterDuration)) { width ->
                            direction * width / 14
                        }).togetherWith(
                            fadeOut(tween(exitDuration)) + slideOutHorizontally(tween(exitDuration)) { width ->
                                -direction * width / 18
                            },
                        )
                    },
                    label = "luoshuPageTransition",
                ) { target ->
                    when (target) {
                        AppPage.Home -> HomeRoute(
                            style = appearance.uiStyle,
                            state = viewModel.snapshot.toHomeUiState(features.systemWeight),
                            actions = homeActions,
                        )
                        AppPage.Library -> Box(
                            modifier = Modifier.fillMaxSize().padding(bottom = libraryDockClearance),
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
                        AppPage.Studio -> FontStudioRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toFontStudioUiState(features),
                            actions = studioActions,
                        )
                        AppPage.Logs -> LogsRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toLogsUiState(),
                            actions = logsActions,
                        )
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

            if (page == AppPage.Studio) {
                NativeImportOverlay(
                    viewModel = viewModel,
                    style = appearance.uiStyle,
                    modifier = Modifier
                        .align(Alignment.BottomEnd)
                        .navigationBarsPadding()
                        .padding(end = 18.dp, bottom = 166.dp),
                )
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
                if (miuix) return@drawBehind
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
    val shape = if (floating) RoundedCornerShape(30.dp) else RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
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
        itemHeight = 58.dp,
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
    val shape = if (floating) RoundedCornerShape(29.dp) else RoundedCornerShape(topStart = 29.dp, topEnd = 29.dp)
    val activeHaze = appearance.blurEnabled && appearance.glassEnabled
    val hazeModifier = if (activeHaze) {
        Modifier.hazeEffect(state = hazeState, style = HazeMaterials.ultraThin()) {
            blurRadius = 24.dp
            noiseFactor = .035f
        }
    } else Modifier

    AppDockLayout(
        pages = dockPages,
        current = current,
        onSelect = onSelect,
        itemHeight = 56.dp,
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 14.dp).padding(bottom = bottomInset + 8.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) 12.dp else 5.dp, shape, clip = false)
            .clip(shape)
            .then(hazeModifier)
            .background(
                if (activeHaze) tokens.elevatedCardBackground.copy(alpha = if (dark) .48f else .66f)
                else tokens.elevatedCardBackground.copy(alpha = .98f),
            )
            .border(1.dp, if (dark) Color.White.copy(alpha = .10f) else Color.White.copy(alpha = .58f), shape)
            .padding(start = 5.dp, top = 5.dp, end = 5.dp, bottom = if (floating) 5.dp else bottomInset + 5.dp),
        indicatorColor = scheme.primary.copy(alpha = if (dark) .20f else .12f),
        selectedColor = scheme.primary,
        unselectedColor = scheme.onSurfaceVariant.copy(alpha = .82f),
        label = "luoshuMiuixDockIndicator",
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
    selectedColor: Color,
    unselectedColor: Color,
    label: String,
) {
    BoxWithConstraints(modifier = modifier) {
        val itemWidth = maxWidth / pages.size.toFloat()
        val targetIndex = pages.indexOf(current).coerceAtLeast(0)
        val indicatorX by animateDpAsState(
            targetValue = itemWidth * targetIndex.toFloat(),
            animationSpec = spring(dampingRatio = .76f, stiffness = Spring.StiffnessMediumLow),
            label = label,
        )
        Box(
            modifier = Modifier
                .offset(x = indicatorX + 5.dp)
                .width(itemWidth - 10.dp)
                .height(itemHeight)
                .clip(RoundedCornerShape(20.dp))
                .background(indicatorColor),
        )
        Row(Modifier.fillMaxWidth()) {
            pages.forEach { page ->
                val selected = current == page
                Column(
                    modifier = Modifier
                        .width(itemWidth)
                        .height(itemHeight)
                        .clip(RoundedCornerShape(20.dp))
                        .clickable { onSelect(page) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Icon(
                        page.icon,
                        contentDescription = page.label,
                        modifier = Modifier.size(if (selected) 22.dp else 20.dp),
                        tint = if (selected) selectedColor else unselectedColor,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        page.label,
                        color = if (selected) selectedColor else unselectedColor,
                        fontSize = 11.sp,
                        fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                        maxLines = 1,
                    )
                }
            }
        }
    }
}
