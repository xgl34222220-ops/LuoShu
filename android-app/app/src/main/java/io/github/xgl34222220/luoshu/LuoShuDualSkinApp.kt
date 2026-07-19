package io.github.xgl34222220.luoshu

import android.view.Gravity
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
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.List
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.TextFields
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
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
import io.github.xgl34222220.luoshu.ui.appearance.LocalAppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.home.HomeActions
import io.github.xgl34222220.luoshu.ui.home.HomeRoute
import io.github.xgl34222220.luoshu.ui.home.toHomeUiState
import io.github.xgl34222220.luoshu.ui.settings.AppearanceActions
import io.github.xgl34222220.luoshu.ui.settings.AppearanceSettingsRoute
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTheme
import kotlin.math.abs
import kotlin.math.roundToInt

private enum class DualPage(val label: String, val icon: ImageVector) {
    Home("首页", Icons.Rounded.Home),
    Library("字体库", Icons.Rounded.List),
    Studio("组合", Icons.Rounded.Layers),
    Logs("日志", Icons.Rounded.Description),
    Settings("设置", Icons.Rounded.Settings),
}

@Composable
internal fun LuoShuDualSkinApp(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    appearanceViewModel: AppearanceViewModel,
) {
    val appearance by appearanceViewModel.settings.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf(DualPage.Home) }
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
            DualPage.Home -> features.refreshSystemWeight()
            DualPage.Library -> viewModel.ensureFonts()
            DualPage.Studio -> {
                viewModel.ensureFonts()
                viewModel.refreshMixConfig()
            }
            DualPage.Logs -> viewModel.refreshLogs()
            DualPage.Settings -> Unit
        }
    }
    BackHandler(enabled = page != DualPage.Home) { page = DualPage.Home }

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
                DualBackdrop(appearance, dark)
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
                    label = "luoshuDualSkinPage",
                ) { target ->
                    when (target) {
                        DualPage.Home -> HomeRoute(
                            style = appearance.uiStyle,
                            state = viewModel.snapshot.toHomeUiState(features.systemWeight),
                            actions = HomeActions(
                                refresh = {
                                    viewModel.refresh()
                                    features.refreshSystemWeight()
                                },
                                openFontLibrary = { page = DualPage.Library },
                                openFontStudio = { page = DualPage.Studio },
                                openLogs = { page = DualPage.Logs },
                                restoreDefault = { restoreDefault = true },
                                reboot = viewModel::rebootDevice,
                                previewSystemWeight = features::previewSystemWeight,
                                resetSystemWeight = features::resetSystemWeight,
                            ),
                        )
                        DualPage.Library -> SharedFontLibraryPage(
                            viewModel = viewModel,
                            appearance = appearance,
                            onApply = { pendingApply = it },
                            onDelete = { pendingDelete = it },
                            onRestoreDefault = { restoreDefault = true },
                        )
                        DualPage.Studio -> SharedFontStudioPage(
                            viewModel = viewModel,
                            features = features,
                            appearance = appearance,
                            onPick = { pickerSlot = it },
                        )
                        DualPage.Logs -> SharedLogsPage(
                            logs = viewModel.logs,
                            appearance = appearance,
                            onRefresh = viewModel::refreshLogs,
                        )
                        DualPage.Settings -> AppearanceSettingsRoute(
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
                MaterialGlassDock(
                    current = page,
                    onSelect = { page = it },
                    appearance = appearance,
                    hazeState = hazeState,
                    modifier = Modifier.align(Alignment.BottomCenter),
                )
            } else {
                MiuixLiquidDock(
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
            DualFontPicker(
                slot = slot,
                fonts = viewModel.fonts.filter { it.valid },
                selected = selectedFontIdDual(viewModel.mixState, slot),
                onDismiss = { pickerSlot = null },
                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(
                        slot,
                        normalizedWeightDual(font, selectedWeightDual(viewModel.mixState, slot)),
                    )
                    pickerSlot = null
                },
            )
        }
    }
}

@Composable
private fun DualBackdrop(appearance: AppearanceSettings, dark: Boolean) {
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
private fun MaterialGlassDock(
    current: DualPage,
    onSelect: (DualPage) -> Unit,
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
    } else {
        Modifier
    }
    BoxWithConstraints(
        modifier = modifier
            .then(
                if (floating) Modifier.padding(horizontal = 16.dp).padding(bottom = bottomInset + 10.dp)
                else Modifier,
            )
            .fillMaxWidth()
            .shadow(if (floating) 18.dp else 7.dp, shape, clip = false)
            .clip(shape)
            .then(hazeModifier)
            .background(
                when {
                    activeHaze && dark -> scheme.surface.copy(alpha = .34f)
                    activeHaze -> Color.White.copy(alpha = .26f)
                    dark -> scheme.surface.copy(alpha = .98f)
                    else -> scheme.surface.copy(alpha = .98f)
                },
            )
            .border(1.dp, if (dark) Color.White.copy(alpha = .12f) else Color.White.copy(alpha = .78f), shape)
            .padding(
                start = 6.dp,
                top = 7.dp,
                end = 6.dp,
                bottom = if (floating) 7.dp else bottomInset + 7.dp,
            ),
    ) {
        Row(Modifier.fillMaxWidth()) {
            DualPage.entries.forEach { page ->
                val selected = current == page
                Column(
                    modifier = Modifier
                        .width(maxWidth / DualPage.entries.size.toFloat())
                        .height(58.dp)
                        .clip(RoundedCornerShape(22.dp))
                        .background(if (selected) scheme.primaryContainer.copy(alpha = .62f) else Color.Transparent)
                        .clickable { onSelect(page) },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Icon(
                        imageVector = page.icon,
                        contentDescription = page.label,
                        modifier = Modifier.size(if (selected) 22.dp else 20.dp),
                        tint = if (selected) scheme.primary else scheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        text = page.label,
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
private fun MiuixLiquidDock(
    current: DualPage,
    onSelect: (DualPage) -> Unit,
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
            .then(
                if (floating) Modifier.padding(horizontal = 16.dp).padding(bottom = bottomInset + 10.dp)
                else Modifier,
            )
            .fillMaxWidth()
            .shadow(if (floating) 22.dp else 8.dp, shape, clip = false)
            .clip(shape)
            .background(tokens.elevatedCardBackground.copy(alpha = .98f))
            .border(1.dp, if (dark) Color.White.copy(alpha = .12f) else Color.White.copy(alpha = .82f), shape)
            .padding(
                start = 6.dp,
                top = 7.dp,
                end = 6.dp,
                bottom = if (floating) 7.dp else bottomInset + 7.dp,
            ),
    ) {
        val itemWidth = maxWidth / DualPage.entries.size.toFloat()
        val targetIndex = current.ordinal.coerceIn(DualPage.entries.indices)
        val indicatorX by animateDpAsState(
            targetValue = itemWidth * targetIndex.toFloat(),
            animationSpec = spring(dampingRatio = .72f, stiffness = Spring.StiffnessMediumLow),
            label = "luoshuMiuixDockIndicator",
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
            DualPage.entries.forEach { page ->
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
                        imageVector = page.icon,
                        contentDescription = page.label,
                        modifier = Modifier.size(if (selected) 22.dp else 20.dp),
                        tint = if (selected) scheme.primary else scheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        text = page.label,
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
private fun DualPageHeader(
    eyebrow: String,
    title: String,
    subtitle: String,
    appearance: AppearanceSettings,
    onRefresh: (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(horizontal = if (appearance.uiStyle == UiStyle.MIUIX) 20.dp else 22.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                eyebrow.uppercase(),
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
            )
            Spacer(Modifier.height(5.dp))
            Text(
                title,
                fontSize = if (appearance.uiStyle == UiStyle.MIUIX) 34.sp else 32.sp,
                lineHeight = if (appearance.uiStyle == UiStyle.MIUIX) 39.sp else 37.sp,
                fontWeight = FontWeight.Black,
            )
            Spacer(Modifier.height(4.dp))
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        }
        if (onRefresh != null) {
            Surface(
                shape = RoundedCornerShape(if (appearance.uiStyle == UiStyle.MIUIX) 18.dp else 20.dp),
                color = if (appearance.uiStyle == UiStyle.MIUIX) LocalMiuixTokens.current.elevatedCardBackground
                else MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .82f),
                shadowElevation = 6.dp,
            ) {
                IconButton(onClick = onRefresh, modifier = Modifier.size(56.dp)) {
                    Icon(Icons.Rounded.Refresh, contentDescription = "刷新", modifier = Modifier.size(26.dp))
                }
            }
        }
    }
}

@Composable
private fun DualCard(
    appearance: AppearanceSettings,
    modifier: Modifier = Modifier,
    padding: PaddingValues = PaddingValues(18.dp),
    content: @Composable () -> Unit,
) {
    Surface(
        modifier = modifier,
        shape = if (appearance.uiStyle == UiStyle.MIUIX) RoundedCornerShape(34.dp) else MaterialTheme.shapes.extraLarge,
        color = if (appearance.uiStyle == UiStyle.MIUIX) LocalMiuixTokens.current.cardBackground
        else MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f),
        tonalElevation = if (appearance.uiStyle == UiStyle.MATERIAL) 2.dp else 0.dp,
        shadowElevation = if (appearance.uiStyle == UiStyle.MIUIX) 7.dp else 4.dp,
        border = BorderStroke(
            1.dp,
            MaterialTheme.colorScheme.outlineVariant.copy(alpha = if (appearance.uiStyle == UiStyle.MIUIX) .22f else .38f),
        ),
    ) {
        Box(Modifier.padding(padding)) { content() }
    }
}

@Composable
private fun SharedFontLibraryPage(
    viewModel: LuoShuViewModel,
    appearance: AppearanceSettings,
    onApply: (FontItem) -> Unit,
    onDelete: (FontItem) -> Unit,
    onRestoreDefault: () -> Unit,
) {
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = bottomInset + 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            DualPageHeader(
                "FONT LIBRARY",
                "字体库",
                "导入、预览和直接应用",
                appearance,
                { viewModel.refreshFonts(force = true) },
            )
        }
        item {
            DualCard(
                appearance = appearance,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                padding = PaddingValues(8.dp),
            ) {
                OutlinedTextField(
                    value = viewModel.searchQuery,
                    onValueChange = viewModel::setSearchQuery,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = RoundedCornerShape(if (appearance.uiStyle == UiStyle.MIUIX) 18.dp else 16.dp),
                    leadingIcon = { Icon(Icons.Rounded.Search, null) },
                    placeholder = { Text("搜索字体名称或格式") },
                )
            }
        }
        if (viewModel.fontLoading || viewModel.operationBusy) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        }
        if (viewModel.fontError.isNotBlank()) {
            item { DualError(viewModel.fontError) }
        }
        if (viewModel.operationMessage.isNotBlank()) {
            item { DualOperation(viewModel) }
        }
        item {
            DualCard(
                appearance = appearance,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(54.dp),
                        shape = RoundedCornerShape(19.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Text("系", fontSize = 21.sp, fontWeight = FontWeight.Black)
                        }
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text("系统默认字体", fontSize = 17.sp, fontWeight = FontWeight.Black)
                        Text("恢复 ROM 原始字体映射", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                    }
                    if (viewModel.snapshot.activeFont == "default") {
                        DualPill("使用中", Color(0xFF2DBE87))
                    } else {
                        Button(
                            onClick = onRestoreDefault,
                            enabled = !viewModel.operationBusy,
                            shape = RoundedCornerShape(17.dp),
                        ) { Text("恢复") }
                    }
                }
            }
        }
        if (!viewModel.fontLoading && viewModel.filteredFonts.isEmpty()) {
            item {
                DualCard(
                    appearance = appearance,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                    padding = PaddingValues(34.dp),
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            Icons.Rounded.FontDownload,
                            null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(38.dp),
                        )
                        Spacer(Modifier.height(12.dp))
                        Text("没有找到字体", fontSize = 19.sp, fontWeight = FontWeight.Black)
                        Text(
                            "使用右下角导入按钮选择 TTF、OTF、TTC 或模块 ZIP",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            textAlign = TextAlign.Center,
                        )
                    }
                }
            }
        }
        items(viewModel.filteredFonts, key = { it.id }) { font ->
            DualFontCard(
                font = font,
                active = viewModel.snapshot.activeFont == font.id,
                busy = viewModel.operationBusy || viewModel.mixState.busy,
                appearance = appearance,
                onApply = { onApply(font) },
                onDelete = { onDelete(font) },
            )
        }
    }
}

@Composable
private fun DualFontCard(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    appearance: AppearanceSettings,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    DualCard(
        appearance = appearance,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(font.name, fontWeight = FontWeight.Black, fontSize = 16.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) {
                    IconButton(onClick = onDelete, enabled = !busy) {
                        Icon(Icons.Rounded.Delete, contentDescription = "删除", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(24.dp),
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = .035f),
            ) {
                NativeFontPreview(
                    font = font,
                    text = "洛书字体预览\nHello 0123456789",
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier.fillMaxWidth().height(94.dp).padding(horizontal = 17.dp, vertical = 12.dp),
                    textSizeSp = 24f,
                    maxLines = 2,
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                DualPill(capabilityLabelDual(font), MaterialTheme.colorScheme.primary)
                Spacer(Modifier.weight(1f))
                if (active) {
                    Text("当前使用", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black, fontSize = 12.sp)
                } else {
                    Button(onClick = onApply, enabled = font.valid && !busy, shape = RoundedCornerShape(17.dp)) {
                        Text("应用字体", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun SharedFontStudioPage(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    appearance: AppearanceSettings,
    onPick: (MixSlot) -> Unit,
) {
    val state = viewModel.mixState
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val direct = directApplyFontIdDual(state)
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = bottomInset + 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            DualPageHeader(
                "FONT MIX",
                "字体组合",
                "中文、英文、数字与真实设计轴",
                appearance,
                viewModel::refreshMixConfig,
            )
        }
        if (viewModel.fontLoading || state.loading) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        }
        if (state.error.isNotBlank()) {
            item { DualError(state.error) }
        }
        if (state.busy || state.taskState == "success") {
            item {
                DualCard(
                    appearance = appearance,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                ) {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.AutoAwesome, null, tint = MaterialTheme.colorScheme.primary)
                            Spacer(Modifier.width(9.dp))
                            Text(state.message, modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Text("${state.progress}%", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                        Spacer(Modifier.height(12.dp))
                        LinearProgressIndicator(
                            progress = { state.progress / 100f },
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }
        item { DualSlotCard(viewModel, MixSlot.Cjk, "中文基底", "完整中文、符号与回退基底", appearance, onPick) }
        item { DualSlotCard(viewModel, MixSlot.Latin, "英文字形", "替换拉丁字母轮廓", appearance, onPick) }
        item { DualSlotCard(viewModel, MixSlot.Digit, "数字字形", "替换数字与相关标点", appearance, onPick) }
        item { DualCoverageCard(viewModel, features, appearance) }
        item {
            DualCard(
                appearance = appearance,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                padding = PaddingValues(20.dp),
            ) {
                Column {
                    Text(
                        if (direct != null) "同一字体，无需复合" else "生成完整复合字体",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        if (direct != null) "三个槽位均为标准 Regular 400，将直接应用原始字体。"
                        else "当前字重和设计轴会写入最终字体。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                    )
                    Spacer(Modifier.height(18.dp))
                    Button(
                        onClick = {
                            if (direct != null) viewModel.applyFont(direct) else viewModel.startMix()
                        },
                        enabled = !state.busy && !viewModel.operationBusy && viewModel.fonts.isNotEmpty(),
                        modifier = Modifier.fillMaxWidth().height(60.dp),
                        shape = RoundedCornerShape(22.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                    ) {
                        Icon(if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome, null)
                        Spacer(Modifier.width(8.dp))
                        Text(if (direct != null) "直接应用此字体" else "生成并应用到系统", fontSize = 16.sp, fontWeight = FontWeight.Black)
                    }
                }
            }
        }
    }
}

@Composable
private fun DualSlotCard(
    viewModel: LuoShuViewModel,
    slot: MixSlot,
    title: String,
    subtitle: String,
    appearance: AppearanceSettings,
    onPick: (MixSlot) -> Unit,
) {
    val state = viewModel.mixState
    val fontId = selectedFontIdDual(state, slot)
    val font = viewModel.fonts.firstOrNull { it.id == fontId }
    val weight = selectedWeightDual(state, slot)
    val axes = selectedAxesDual(state, slot)
    DualCard(
        appearance = appearance,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = RoundedCornerShape(17.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            when (slot) {
                                MixSlot.Cjk -> "中"
                                MixSlot.Latin -> "Aa"
                                MixSlot.Digit -> "123"
                            },
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Black,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, fontWeight = FontWeight.Black, fontSize = 18.sp)
                    Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                DualPill(font?.let(::capabilityLabelDual) ?: "未选择", MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).clickable(enabled = !state.busy) { onPick(slot) },
                shape = RoundedCornerShape(22.dp),
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = .035f),
            ) {
                Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        font?.name ?: "选择字体",
                        modifier = Modifier.weight(1f),
                        fontWeight = FontWeight.Bold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Icon(Icons.Rounded.KeyboardArrowDown, null)
                }
            }
            if (font != null) {
                Spacer(Modifier.height(12.dp))
                NativeFontPreview(
                    font = font,
                    text = when (slot) {
                        MixSlot.Cjk -> "洛书中文 Aa 0123"
                        MixSlot.Latin -> "LuoShu Typography 0123"
                        MixSlot.Digit -> "0123456789 Aa"
                    },
                    axes = axes,
                    modifier = Modifier.fillMaxWidth().height(74.dp).padding(horizontal = 14.dp),
                    textSizeSp = 25f,
                    gravity = Gravity.CENTER,
                    maxLines = 1,
                )
                Spacer(Modifier.height(12.dp))
                DualWeightControl(
                    font = font,
                    value = weight,
                    axes = axes,
                    enabled = !state.busy,
                    onValue = { viewModel.updateMixWeight(slot, it) },
                    onAxis = { tag, axisValue -> viewModel.updateMixAxis(slot, tag, axisValue) },
                )
            }
        }
    }
}

@Composable
private fun DualWeightControl(
    font: FontItem,
    value: Int,
    axes: Map<String, Float>,
    enabled: Boolean,
    onValue: (Int) -> Unit,
    onAxis: (String, Float) -> Unit,
) {
    val axisInfo = rememberWeightAxisInfo(font)
    when {
        font.variable && axisInfo.loading -> {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(9.dp))
                Text("正在读取真实可变轴…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
        }
        font.variable && axisInfo.axes.isNotEmpty() -> {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                axisInfo.axes.forEach { axis ->
                    val minimum = axis.min.coerceAtMost(axis.max)
                    val maximum = axis.max.coerceAtLeast(axis.min)
                    val current = (axes[axis.tag] ?: axis.default).coerceIn(minimum, maximum)
                    val isWeight = axis.tag == "wght"
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("${axis.tag} · ${axisDisplayNameDual(axis.tag)}", fontWeight = FontWeight.Bold, fontSize = 11.sp)
                            Spacer(Modifier.weight(1f))
                            Text(axisValueLabelDual(current), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                        Slider(
                            value = current,
                            onValueChange = { raw ->
                                val next = if (isWeight) {
                                    ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum)
                                } else raw.coerceIn(minimum, maximum)
                                onAxis(axis.tag, next)
                            },
                            enabled = enabled,
                            valueRange = minimum..maximum,
                            steps = if (isWeight && maximum > minimum) (((maximum - minimum) / 10f).roundToInt() - 1).coerceAtLeast(0) else 0,
                        )
                        Text(
                            "${axisValueLabelDual(minimum)} · 默认 ${axisValueLabelDual(axis.default)} · ${axisValueLabelDual(maximum)}",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 9.sp,
                        )
                    }
                }
            }
        }
        staticWeightsDual(font).size >= 2 -> {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                staticWeightsDual(font).forEach { option ->
                    DualChoiceChip(
                        text = weightNameDual(option),
                        selected = option == value,
                        enabled = enabled,
                    ) { onValue(option) }
                }
            }
        }
        else -> {
            Text(
                "固定 ${weightNameDual(fixedWeightDual(font))}，没有可调设计轴。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 10.sp,
            )
        }
    }
}

@Composable
private fun DualChoiceChip(text: String, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clip(RoundedCornerShape(999.dp)).clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp),
            color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun DualCoverageCard(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    appearance: AppearanceSettings,
) {
    val fontId = viewModel.mixState.cjk
    val font = viewModel.fonts.firstOrNull { it.id == fontId }
    val probe = features.coverage
    DualCard(
        appearance = appearance,
        modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
        padding = PaddingValues(20.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("字形覆盖诊断", fontSize = 18.sp, fontWeight = FontWeight.Black)
                    Text(
                        font?.name ?: "请先选择中文基底",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                OutlinedButton(
                    onClick = { if (fontId.isNotBlank()) features.inspectCoverage(fontId) },
                    enabled = fontId.isNotBlank() && !probe.loading,
                    shape = RoundedCornerShape(17.dp),
                ) {
                    if (probe.loading) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    else Text("检测")
                }
            }
            val metrics = probe.metrics.takeIf { probe.fontId == fontId }
            if (metrics != null) {
                Spacer(Modifier.height(14.dp))
                DualCoverageRow("中文", metrics.cjkRatio)
                DualCoverageRow("英文", metrics.latinRatio)
                DualCoverageRow("数字", metrics.digitRatio)
                DualCoverageRow("标点", metrics.punctuationRatio)
            } else if (probe.error.isNotBlank() && probe.fontId == fontId) {
                Spacer(Modifier.height(12.dp))
                Text(probe.error, color = MaterialTheme.colorScheme.error, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun DualCoverageRow(label: String, ratio: Float) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.width(42.dp), fontSize = 11.sp, fontWeight = FontWeight.Bold)
        LinearProgressIndicator(
            progress = { ratio },
            modifier = Modifier.weight(1f).height(7.dp).clip(RoundedCornerShape(999.dp)),
        )
        Spacer(Modifier.width(10.dp))
        Text("${(ratio * 100).roundToInt()}%", color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun SharedLogsPage(logs: String, appearance: AppearanceSettings, onRefresh: () -> Unit) {
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    Column(Modifier.fillMaxSize()) {
        DualPageHeader("DIAGNOSTICS", "运行日志", "字体任务与错误记录", appearance, onRefresh)
        DualCard(
            appearance = appearance,
            modifier = Modifier.fillMaxSize().padding(horizontal = 18.dp).padding(bottom = bottomInset + 106.dp),
        ) {
            SelectionContainer {
                Text(
                    logs,
                    modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                    fontFamily = FontFamily.Monospace,
                    fontSize = 10.sp,
                    lineHeight = 15.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun DualFontPicker(
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
                Modifier.fillMaxWidth().heightIn(max = 470.dp),
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
                                Text(capabilityLabelDual(font), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                            }
                            if (font.id == selected) Icon(Icons.Rounded.CheckCircle, null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
}

@Composable
private fun DualOperation(viewModel: LuoShuViewModel) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
        shape = RoundedCornerShape(25.dp),
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            if (viewModel.operationBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            else Icon(Icons.Rounded.CheckCircle, null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(10.dp))
            Text(viewModel.operationMessage, modifier = Modifier.weight(1f), fontSize = 12.sp)
        }
    }
}

@Composable
private fun DualError(message: String) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
        shape = RoundedCornerShape(25.dp),
        color = MaterialTheme.colorScheme.errorContainer.copy(alpha = .88f),
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.Warning, null, tint = MaterialTheme.colorScheme.error)
            Spacer(Modifier.width(10.dp))
            Text(message, modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer, fontSize = 12.sp)
        }
    }
}

@Composable
private fun DualPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .12f)) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
        )
    }
}

private fun selectedFontIdDual(state: MixState, slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> state.cjk
    MixSlot.Latin -> state.latin
    MixSlot.Digit -> state.digit
}

private fun selectedWeightDual(state: MixState, slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> state.cjkWeight
    MixSlot.Latin -> state.latinWeight
    MixSlot.Digit -> state.digitWeight
}

private fun selectedAxesDual(state: MixState, slot: MixSlot): Map<String, Float> = when (slot) {
    MixSlot.Cjk -> state.cjkAxes
    MixSlot.Latin -> state.latinAxes
    MixSlot.Digit -> state.digitAxes
}

private fun directApplyFontIdDual(state: MixState): String? {
    val ids = listOf(state.cjk, state.latin, state.digit)
    if (ids.any { it.isBlank() } || ids.distinct().size != 1) return null
    if (listOf(state.cjkWeight, state.latinWeight, state.digitWeight).any { it != 400 }) return null
    val standard = listOf(state.cjkAxes, state.latinAxes, state.digitAxes).all { axes ->
        axes.all { (tag, value) -> tag == "wght" && abs(value - 400f) < .5f }
    }
    return ids.first().takeIf { standard }
}

private fun staticWeightsDual(font: FontItem): List<Int> = font.weights
    .filterNot { it == "variable" }
    .map(::roleWeightDual)
    .distinct()
    .sorted()

private fun fixedWeightDual(font: FontItem): Int = staticWeightsDual(font).firstOrNull() ?: 400

private fun normalizedWeightDual(font: FontItem, current: Int): Int = when {
    font.variable -> current.coerceIn(100, 900)
    staticWeightsDual(font).size >= 2 -> staticWeightsDual(font).minByOrNull { abs(it - current) } ?: 400
    else -> fixedWeightDual(font)
}

private fun capabilityLabelDual(font: FontItem): String = when {
    font.variable -> "可变字体"
    staticWeightsDual(font).size >= 2 -> "${staticWeightsDual(font).size} 档静态字重"
    else -> "固定 ${weightNameDual(fixedWeightDual(font))}"
}

private fun roleWeightDual(role: String): Int = when (role.lowercase()) {
    "thin" -> 100
    "extralight" -> 200
    "light" -> 300
    "regular", "normal" -> 400
    "medium" -> 500
    "semibold" -> 600
    "bold" -> 700
    "extrabold" -> 800
    "black", "heavy" -> 900
    else -> role.toIntOrNull()?.coerceIn(1, 1000) ?: 400
}

private fun weightNameDual(weight: Int): String = when (weight) {
    100 -> "极细 100"
    200 -> "超细 200"
    300 -> "细体 300"
    400 -> "常规 400"
    500 -> "中等 500"
    600 -> "半粗 600"
    700 -> "粗体 700"
    800 -> "特粗 800"
    900 -> "黑体 900"
    else -> weight.toString()
}

private fun axisDisplayNameDual(tag: String): String = when (tag) {
    "wght" -> "字重"
    "wdth" -> "字宽"
    "opsz" -> "光学尺寸"
    "slnt" -> "倾斜"
    "ital" -> "斜体"
    "GRAD" -> "笔画等级"
    else -> "设计轴"
}

private fun axisValueLabelDual(value: Float): String =
    if (value % 1f == 0f) value.roundToInt().toString()
    else value.toString().trimEnd('0').trimEnd('.')
