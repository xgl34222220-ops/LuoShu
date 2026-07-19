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
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.List
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.text.style.TextOverflow
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

private enum class Stage2Page(val label: String, val icon: ImageVector) {
    Home("首页", Icons.Rounded.Home),
    Library("字体库", Icons.Rounded.List),
    Studio("组合", Icons.Rounded.Layers),
    Logs("日志", Icons.Rounded.Description),
    Settings("设置", Icons.Rounded.Settings),
}

@Composable
internal fun LuoShuStage2App(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    appearanceViewModel: AppearanceViewModel,
) {
    val appearance by appearanceViewModel.settings.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf(Stage2Page.Home) }
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
            Stage2Page.Home -> features.refreshSystemWeight()
            Stage2Page.Library -> viewModel.ensureFonts()
            Stage2Page.Studio -> {
                viewModel.ensureFonts()
                viewModel.refreshMixConfig()
            }
            Stage2Page.Logs -> viewModel.refreshLogs()
            Stage2Page.Settings -> Unit
        }
    }
    BackHandler(enabled = page != Stage2Page.Home) { page = Stage2Page.Home }

    LuoShuTheme(appearance) {
        val dark = MaterialTheme.colorScheme.background.luminance() < .5f
        val hazeState = rememberHazeState(
            blurEnabled = appearance.blurEnabled && appearance.glassEnabled,
        )
        Box(Modifier.fillMaxSize()) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .hazeSource(state = hazeState),
            ) {
                Stage2Backdrop(appearance, dark)
                AnimatedContent(
                    targetState = page,
                    modifier = Modifier.fillMaxSize(),
                    contentKey = { it },
                    transitionSpec = {
                        val direction = if (targetState.ordinal >= initialState.ordinal) 1 else -1
                        val enterDuration = if (appearance.uiStyle == UiStyle.MIUIX) 300 else 250
                        val exitDuration = if (appearance.uiStyle == UiStyle.MIUIX) 210 else 170
                        (fadeIn(tween(enterDuration)) + slideInHorizontally(tween(enterDuration)) { width ->
                            direction * width / if (appearance.uiStyle == UiStyle.MIUIX) 8 else 11
                        }).togetherWith(
                            fadeOut(tween(exitDuration)) + slideOutHorizontally(tween(exitDuration)) { width ->
                                -direction * width / if (appearance.uiStyle == UiStyle.MIUIX) 13 else 16
                            },
                        )
                    },
                    label = "luoshuStage2Page",
                ) { target ->
                    when (target) {
                        Stage2Page.Home -> HomeRoute(
                            style = appearance.uiStyle,
                            state = viewModel.snapshot.toHomeUiState(features.systemWeight),
                            actions = HomeActions(
                                refresh = {
                                    viewModel.refresh()
                                    features.refreshSystemWeight()
                                },
                                openFontLibrary = { page = Stage2Page.Library },
                                openFontStudio = { page = Stage2Page.Studio },
                                openLogs = { page = Stage2Page.Logs },
                                restoreDefault = { restoreDefault = true },
                                reboot = viewModel::rebootDevice,
                                previewSystemWeight = features::previewSystemWeight,
                                resetSystemWeight = features::resetSystemWeight,
                            ),
                        )
                        Stage2Page.Library -> FontLibraryRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toFontLibraryUiState(),
                            actions = FontLibraryActions(
                                refresh = { viewModel.refreshFonts(force = true) },
                                setQuery = viewModel::setSearchQuery,
                                apply = { pendingApply = it },
                                delete = { pendingDelete = it },
                                restoreDefault = { restoreDefault = true },
                            ),
                        )
                        Stage2Page.Studio -> FontStudioRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toFontStudioUiState(features),
                            actions = FontStudioActions(
                                refresh = viewModel::refreshMixConfig,
                                pickSlot = { pickerSlot = it },
                                updateWeight = viewModel::updateMixWeight,
                                updateAxis = viewModel::updateMixAxis,
                                inspectCoverage = features::inspectCoverage,
                                startMix = viewModel::startMix,
                                applyDirect = viewModel::applyFont,
                            ),
                        )
                        Stage2Page.Logs -> LogsRoute(
                            style = appearance.uiStyle,
                            state = viewModel.toLogsUiState(),
                            actions = LogsActions(refresh = viewModel::refreshLogs),
                        )
                        Stage2Page.Settings -> AppearanceSettingsRoute(
                            settings = appearance,
                            actions = AppearanceActions(
                                setUiStyle = appearanceViewModel::setUiStyle,
                                setThemeMode = appearanceViewModel::setThemeMode,
                                setSeedArgb = appearanceViewModel::setSeedArgb,
                                setKolorStyle = appearanceViewModel::setKolorStyle,
                                setMonetEnabled = appearanceViewModel::setMonetEnabled,
                                setAmoledBlack = appearanceViewModel::setAmoledBlack,
                                setBlurEnabled = appearanceViewModel::setBlurEnabled,
                                setGlassEnabled = appearanceViewModel::setGlassEnabled,
                                setFloatingDock = appearanceViewModel::setFloatingDock,
                            ),
                        )
                    }
                }
            }

            if (appearance.uiStyle == UiStyle.MATERIAL) {
                Stage2MaterialDock(
                    current = page,
                    onSelect = { page = it },
                    appearance = appearance,
                    hazeState = hazeState,
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            } else {
                Stage2MiuixDock(
                    current = page,
                    onSelect = { page = it },
                    appearance = appearance,
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            }
        }

        pendingApply?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingApply = null },
                title = { Text("应用字体", fontWeight = FontWeight.Black) },
                text = { Text("直接应用「${font.name}」。准备完成后需要完整重启手机。") },
                confirmButton = {
                    TextButton(onClick = {
                        pendingApply = null
                        viewModel.applyFont(font.id)
                    }) { Text("应用") }
                },
                dismissButton = { TextButton(onClick = { pendingApply = null }) { Text("取消") } },
            )
        }

        pendingDelete?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingDelete = null },
                title = { Text("删除字体", fontWeight = FontWeight.Black) },
                text = { Text("确定删除「${font.name}」吗？此操作不可撤销。") },
                confirmButton = {
                    TextButton(onClick = {
                        pendingDelete = null
                        viewModel.deleteFont(font.id)
                    }) { Text("删除", color = MaterialTheme.colorScheme.error) }
                },
                dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("取消") } },
            )
        }

        if (restoreDefault) {
            AlertDialog(
                onDismissRequest = { restoreDefault = false },
                title = { Text("恢复系统字体", fontWeight = FontWeight.Black) },
                text = { Text("恢复 ROM 自带字体映射。完成后需要完整重启手机。") },
                confirmButton = {
                    TextButton(onClick = {
                        restoreDefault = false
                        viewModel.applyFont("default")
                    }) { Text("恢复") }
                },
                dismissButton = { TextButton(onClick = { restoreDefault = false }) { Text("取消") } },
            )
        }

        pickerSlot?.let { slot ->
            Stage2FontPicker(
                slot = slot,
                fonts = viewModel.fonts.filter { it.valid },
                selected = selectedFontId(viewModel.mixState, slot),
                onDismiss = { pickerSlot = null },
                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(
                        slot,
                        fontNormalizedWeight(font, when (slot) {
                            MixSlot.Cjk -> viewModel.mixState.cjkWeight
                            MixSlot.Latin -> viewModel.mixState.latinWeight
                            MixSlot.Digit -> viewModel.mixState.digitWeight
                        }),
                    )
                    pickerSlot = null
                },
            )
        }
    }
}

@Composable
private fun Stage2Backdrop(appearance: AppearanceSettings, dark: Boolean) {
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
private fun Stage2MaterialDock(
    current: Stage2Page,
    onSelect: (Stage2Page) -> Unit,
    appearance: AppearanceSettings,
    hazeState: HazeState,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val floating = appearance.floatingDock
    val shape = if (floating) RoundedCornerShape(32.dp) else RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp)
    val activeHaze = appearance.blurEnabled && appearance.glassEnabled
    val hazeModifier = if (activeHaze) {
        Modifier.hazeEffect(state = hazeState, style = HazeMaterials.ultraThin()) {
            blurRadius = 28.dp
            noiseFactor = .05f
        }
    } else Modifier

    BoxWithConstraints(
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 16.dp).padding(bottom = bottomInset + 10.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) 18.dp else 7.dp, shape, clip = false)
            .clip(shape)
            .then(hazeModifier)
            .background(
                when {
                    activeHaze && dark -> scheme.surface.copy(alpha = .34f)
                    activeHaze -> Color.White.copy(alpha = .26f)
                    else -> scheme.surface.copy(alpha = .98f)
                },
            )
            .border(1.dp, if (dark) Color.White.copy(alpha = .12f) else Color.White.copy(alpha = .78f), shape)
            .padding(start = 6.dp, top = 7.dp, end = 6.dp, bottom = if (floating) 7.dp else bottomInset + 7.dp),
    ) {
        val itemWidth = maxWidth / Stage2Page.entries.size.toFloat()
        Row(Modifier.fillMaxWidth()) {
            Stage2Page.entries.forEach { page ->
                val selected = current == page
                Column(
                    modifier = Modifier
                        .width(itemWidth)
                        .height(58.dp)
                        .clip(RoundedCornerShape(22.dp))
                        .background(if (selected) scheme.primaryContainer.copy(alpha = .62f) else Color.Transparent)
                        .clickable { onSelect(page) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Icon(
                        page.icon,
                        contentDescription = page.label,
                        modifier = Modifier.size(if (selected) 22.dp else 20.dp),
                        tint = if (selected) scheme.primary else scheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        page.label,
                        color = if (selected) scheme.primary else scheme.onSurfaceVariant,
                        fontSize = 9.sp,
                        fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                    )
                }
            }
        }
    }
}

@Composable
private fun Stage2MiuixDock(
    current: Stage2Page,
    onSelect: (Stage2Page) -> Unit,
    appearance: AppearanceSettings,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val floating = appearance.floatingDock
    val shape = if (floating) RoundedCornerShape(34.dp) else RoundedCornerShape(topStart = 34.dp, topEnd = 34.dp)
    BoxWithConstraints(
        modifier = modifier
            .then(if (floating) Modifier.padding(horizontal = 16.dp).padding(bottom = bottomInset + 10.dp) else Modifier)
            .fillMaxWidth()
            .shadow(if (floating) 22.dp else 8.dp, shape, clip = false)
            .clip(shape)
            .background(tokens.elevatedCardBackground.copy(alpha = .98f))
            .border(1.dp, if (dark) Color.White.copy(alpha = .12f) else Color.White.copy(alpha = .82f), shape)
            .padding(start = 6.dp, top = 7.dp, end = 6.dp, bottom = if (floating) 7.dp else bottomInset + 7.dp),
    ) {
        val itemWidth = maxWidth / Stage2Page.entries.size.toFloat()
        val targetIndex = current.ordinal.coerceIn(Stage2Page.entries.indices)
        val indicatorX by animateDpAsState(
            targetValue = itemWidth * targetIndex.toFloat(),
            animationSpec = spring(dampingRatio = .72f, stiffness = Spring.StiffnessMediumLow),
            label = "luoshuStage2MiuixDockIndicator",
        )
        Box(
            modifier = Modifier
                .offset(x = indicatorX + 4.dp)
                .width(itemWidth - 8.dp)
                .height(58.dp)
                .clip(RoundedCornerShape(24.dp))
                .background(
                    Brush.linearGradient(
                        listOf(
                            scheme.primary.copy(alpha = if (dark) .28f else .20f),
                            scheme.tertiary.copy(alpha = if (dark) .20f else .13f),
                        ),
                    ),
                ),
        )
        Row(Modifier.fillMaxWidth()) {
            Stage2Page.entries.forEach { page ->
                val selected = current == page
                Column(
                    modifier = Modifier
                        .width(itemWidth)
                        .height(58.dp)
                        .clip(RoundedCornerShape(24.dp))
                        .clickable { onSelect(page) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Icon(
                        page.icon,
                        contentDescription = page.label,
                        modifier = Modifier.size(if (selected) 22.dp else 20.dp),
                        tint = if (selected) scheme.primary else scheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        page.label,
                        color = if (selected) scheme.primary else scheme.onSurfaceVariant.copy(alpha = .78f),
                        fontSize = 9.sp,
                        fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                    )
                }
            }
        }
    }
}

@Composable
private fun Stage2FontPicker(
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(
                "选择${when (slot) {
                    MixSlot.Cjk -> "中文"
                    MixSlot.Latin -> "英文"
                    MixSlot.Digit -> "数字"
                }}字体",
                fontWeight = FontWeight.Black,
            )
        },
        text = {
            LazyColumn(
                Modifier.fillMaxWidth().height(470.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(fonts, key = { it.id }) { font ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).clickable { onChoose(font) },
                        shape = RoundedCornerShape(20.dp),
                        color = if (font.id == selected) MaterialTheme.colorScheme.primary.copy(alpha = .12f)
                        else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .54f),
                    ) {
                        Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(font.name, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                Text(font.weightLabel, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                            }
                            if (font.id == selected) {
                                Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
}
