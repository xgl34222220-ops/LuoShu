package io.github.xgl34222220.luoshu

import android.os.Build
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
import androidx.compose.foundation.isSystemInDarkTheme
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
import androidx.compose.material.icons.rounded.Palette
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.TextFields
import androidx.compose.material.icons.rounded.Tune
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
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.roundToInt

private enum class Alpha16Page(val label: String, val icon: ImageVector) {
    Home("首页", Icons.Rounded.Home),
    Library("字体库", Icons.Rounded.List),
    Studio("工作台", Icons.Rounded.Layers),
    Logs("日志", Icons.Rounded.Description),
}

private val Alpha16Light = lightColorScheme(
    primary = Color(0xFF426FE8),
    onPrimary = Color.White,
    secondary = Color(0xFF6E5BD5),
    tertiary = Color(0xFF8A5ED8),
    background = Color(0xFFF8F8FC),
    surface = Color(0xFFFEFBFF),
    surfaceVariant = Color(0xFFF0F2F8),
    onSurface = Color(0xFF171923),
    onSurfaceVariant = Color(0xFF666B79),
)

private val Alpha16Dark = darkColorScheme(
    primary = Color(0xFFB7C8FF),
    onPrimary = Color(0xFF17336C),
    secondary = Color(0xFFD1C2FF),
    tertiary = Color(0xFFE3B9FF),
    background = Color(0xFF101117),
    surface = Color(0xFF1A1C24),
    surfaceVariant = Color(0xFF272A34),
    onSurface = Color(0xFFF3F3F7),
    onSurfaceVariant = Color(0xFFB8BAC5),
)

@Composable
internal fun LuoShuAlpha16App(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
) {
    val context = LocalContext.current
    val dark = isSystemInDarkTheme()
    val scheme = remember(dark) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        } else {
            if (dark) Alpha16Dark else Alpha16Light
        }
    }

    var page by rememberSaveable { mutableStateOf(Alpha16Page.Home) }
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
            Alpha16Page.Home -> features.refreshSystemWeight()
            Alpha16Page.Library -> viewModel.ensureFonts()
            Alpha16Page.Studio -> {
                viewModel.ensureFonts()
                viewModel.refreshMixConfig()
            }
            Alpha16Page.Logs -> viewModel.refreshLogs()
        }
    }
    BackHandler(enabled = page != Alpha16Page.Home) { page = Alpha16Page.Home }

    MaterialTheme(colorScheme = scheme) {
        Box(Modifier.fillMaxSize()) {
            Alpha16Backdrop()
            Alpha16AnimatedPage(page, Modifier.fillMaxSize()) { target ->
                when (target) {
                    Alpha16Page.Home -> Alpha16HomePage(
                        viewModel = viewModel,
                        features = features,
                        onOpenLibrary = { page = Alpha16Page.Library },
                        onOpenStudio = { page = Alpha16Page.Studio },
                        onRestoreDefault = { restoreDefault = true },
                    )
                    Alpha16Page.Library -> Alpha16LibraryPage(
                        viewModel = viewModel,
                        onApply = { pendingApply = it },
                        onDelete = { pendingDelete = it },
                        onRestoreDefault = { restoreDefault = true },
                    )
                    Alpha16Page.Studio -> Alpha16StudioPage(
                        viewModel = viewModel,
                        features = features,
                        onPick = { pickerSlot = it },
                    )
                    Alpha16Page.Logs -> Alpha16LogsPage(
                        logs = viewModel.logs,
                        onRefresh = viewModel::refreshLogs,
                    )
                }
            }
            Alpha16LiquidDock(
                current = page,
                onSelect = { page = it },
                modifier = Modifier.align(Alignment.BottomCenter),
            )
        }

        pendingApply?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingApply = null },
                title = { Text("应用字体", fontWeight = FontWeight.Black) },
                text = { Text("直接应用「${font.name}」。准备完成后需要完整重启手机。") },
                confirmButton = {
                    TextButton(
                        onClick = {
                            pendingApply = null
                            viewModel.applyFont(font.id)
                        },
                    ) { Text("应用") }
                },
                dismissButton = {
                    TextButton(onClick = { pendingApply = null }) { Text("取消") }
                },
            )
        }

        pendingDelete?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingDelete = null },
                title = { Text("删除字体", fontWeight = FontWeight.Black) },
                text = { Text("确定删除「${font.name}」吗？此操作不可撤销。") },
                confirmButton = {
                    TextButton(
                        onClick = {
                            pendingDelete = null
                            viewModel.deleteFont(font.id)
                        },
                    ) { Text("删除", color = MaterialTheme.colorScheme.error) }
                },
                dismissButton = {
                    TextButton(onClick = { pendingDelete = null }) { Text("取消") }
                },
            )
        }

        if (restoreDefault) {
            AlertDialog(
                onDismissRequest = { restoreDefault = false },
                title = { Text("恢复系统字体", fontWeight = FontWeight.Black) },
                text = { Text("恢复 ROM 自带字体映射。完成后需要完整重启手机。") },
                confirmButton = {
                    TextButton(
                        onClick = {
                            restoreDefault = false
                            viewModel.applyFont("default")
                        },
                    ) { Text("恢复") }
                },
                dismissButton = {
                    TextButton(onClick = { restoreDefault = false }) { Text("取消") }
                },
            )
        }

        pickerSlot?.let { slot ->
            Alpha16FontPicker(
                slot = slot,
                fonts = viewModel.fonts.filter { it.valid },
                selected = selectedFontId16(viewModel.mixState, slot),
                onDismiss = { pickerSlot = null },
                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(
                        slot,
                        normalizedWeight16(font, selectedWeight16(viewModel.mixState, slot)),
                    )
                    pickerSlot = null
                },
            )
        }
    }
}

@Composable
private fun Alpha16AnimatedPage(
    page: Alpha16Page,
    modifier: Modifier = Modifier,
    content: @Composable (Alpha16Page) -> Unit,
) {
    AnimatedContent(
        targetState = page,
        modifier = modifier,
        contentKey = { it },
        transitionSpec = {
            val direction = if (targetState.ordinal >= initialState.ordinal) 1 else -1
            (fadeIn(tween(300)) + slideInHorizontally(tween(300)) { direction * it / 8 })
                .togetherWith(
                    fadeOut(tween(210)) + slideOutHorizontally(tween(210)) { -direction * it / 13 },
                )
        },
        label = "luoshuPageMotion",
    ) { target -> content(target) }
}

@Composable
private fun Alpha16Backdrop() {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val base = if (dark) {
        listOf(Color(0xFF101117), Color(0xFF151827), Color(0xFF101117))
    } else {
        listOf(Color(0xFFF8F7FF), Color(0xFFF0F5FF), Color(0xFFF8F8FC))
    }
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(base))
            .drawBehind {
                drawRect(
                    Brush.radialGradient(
                        listOf(
                            scheme.secondary.copy(alpha = if (dark) .15f else .24f),
                            Color.Transparent,
                        ),
                        center = Offset(size.width * .9f, size.height * .06f),
                        radius = size.width * .72f,
                    ),
                )
                drawRect(
                    Brush.radialGradient(
                        listOf(
                            scheme.primary.copy(alpha = if (dark) .12f else .18f),
                            Color.Transparent,
                        ),
                        center = Offset(size.width * .02f, size.height * .54f),
                        radius = size.width * .82f,
                    ),
                )
                drawRect(
                    Brush.radialGradient(
                        listOf(
                            scheme.tertiary.copy(alpha = if (dark) .06f else .12f),
                            Color.Transparent,
                        ),
                        center = Offset(size.width, size.height),
                        radius = size.width * .72f,
                    ),
                )
            },
    )
}

@Composable
private fun Alpha16LiquidDock(
    current: Alpha16Page,
    onSelect: (Alpha16Page) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val pages = Alpha16Page.entries
    val shape = RoundedCornerShape(34.dp)

    BoxWithConstraints(
        modifier = modifier
            .padding(horizontal = 16.dp)
            .padding(bottom = bottomInset + 10.dp)
            .fillMaxWidth()
            .shadow(22.dp, shape, clip = false)
            .clip(shape)
            .background(
                if (dark) scheme.surface.copy(alpha = .97f) else Color.White.copy(alpha = .97f),
            )
            .border(
                1.dp,
                if (dark) Color.White.copy(alpha = .14f) else Color.White.copy(alpha = .82f),
                shape,
            )
            .drawBehind {
                drawRoundRect(
                    brush = Brush.verticalGradient(
                        listOf(
                            Color.White.copy(alpha = if (dark) .13f else .46f),
                            Color.Transparent,
                        ),
                    ),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(34.dp.toPx()),
                    size = size.copy(height = size.height * .58f),
                )
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(scheme.primary.copy(alpha = .14f), Color.Transparent),
                        center = Offset(size.width * .18f, size.height * .08f),
                        radius = size.width * .6f,
                    ),
                    radius = size.width * .6f,
                    center = Offset(size.width * .18f, size.height * .08f),
                )
            }
            .padding(7.dp),
    ) {
        val itemWidth = maxWidth / pages.size.toFloat()
        val target = current.ordinal.coerceIn(pages.indices)
        val indicatorX by animateDpAsState(
            targetValue = itemWidth * target.toFloat(),
            animationSpec = spring(
                dampingRatio = .72f,
                stiffness = Spring.StiffnessMediumLow,
            ),
            label = "luoshuDockIndicator",
        )

        Box(
            Modifier
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
                )
                .border(
                    1.dp,
                    Color.White.copy(alpha = if (dark) .12f else .62f),
                    RoundedCornerShape(24.dp),
                ),
        )

        Row(Modifier.fillMaxWidth()) {
            pages.forEach { page ->
                val active = page == current
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
                        modifier = Modifier.size(if (active) 23.dp else 21.dp),
                        tint = if (active) scheme.primary else scheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        text = page.label,
                        color = if (active) scheme.primary else scheme.onSurfaceVariant.copy(alpha = .78f),
                        fontSize = 10.sp,
                        lineHeight = 12.sp,
                        fontWeight = if (active) FontWeight.Bold else FontWeight.Medium,
                    )
                }
            }
        }
    }
}

@Composable
private fun Alpha16Header(
    eyebrow: String,
    title: String,
    subtitle: String,
    onRefresh: (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(horizontal = 22.dp, vertical = 14.dp),
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
                color = MaterialTheme.colorScheme.onSurface,
                fontSize = 34.sp,
                lineHeight = 38.sp,
                fontWeight = FontWeight.Black,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                subtitle,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
            )
        }
        if (onRefresh != null) {
            Alpha16Glass(shape = RoundedCornerShape(18.dp), shadow = 6) {
                IconButton(onClick = onRefresh, modifier = Modifier.size(58.dp)) {
                    Icon(
                        Icons.Rounded.Refresh,
                        contentDescription = "刷新",
                        modifier = Modifier.size(27.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun Alpha16Glass(
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = RoundedCornerShape(30.dp),
    shadow: Int = 10,
    contentPadding: PaddingValues = PaddingValues(0.dp),
    content: @Composable () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val fill = if (dark) Color(0xFF1B1D25) else Color(0xFFF9F9FD)
    val outline = if (dark) Color.White.copy(alpha = .08f) else scheme.primary.copy(alpha = .08f)
    Box(
        modifier
            .shadow(shadow.dp, shape, clip = false)
            .clip(shape)
            .background(fill)
            .border(1.dp, outline, shape)
            .padding(contentPadding),
    ) { content() }
}

@Composable
private fun Alpha16HomePage(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    onOpenLibrary: () -> Unit,
    onOpenStudio: () -> Unit,
    onRestoreDefault: () -> Unit,
) {
    val snapshot = viewModel.snapshot
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = bottomInset + 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Alpha16Header(
                "FONT ENGINE",
                "洛书",
                "Miuix 字体控制中心",
                viewModel::refresh,
            )
        }
        item {
            Alpha16OverviewHero(snapshot)
        }
        if (snapshot.error.isNotBlank()) {
            item { Alpha16Error(snapshot.error) }
        }
        if (viewModel.operationMessage.isNotBlank()) {
            item { Alpha16Operation(viewModel) }
        }
        item {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Alpha16Metric(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Security,
                    label = "Root",
                    value = if (snapshot.rootGranted) snapshot.rootManager else "未授权",
                )
                Alpha16Metric(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Layers,
                    label = "引擎",
                    value = snapshot.mountEngine,
                )
            }
        }
        item {
            Alpha16SectionHeader("QUICK ACCESS", "常用入口", "保持首页简洁")
        }
        item {
            Alpha16ActionGroup(
                items = listOf(
                    Alpha16ActionItem(
                        Icons.Rounded.List,
                        "字体库",
                        "浏览、预览和直接应用字体",
                        onOpenLibrary,
                    ),
                    Alpha16ActionItem(
                        Icons.Rounded.Tune,
                        "字体工作台",
                        "中文、英文、数字与真实设计轴",
                        onOpenStudio,
                    ),
                ),
            )
        }
        item {
            Alpha16SectionHeader("SYSTEM WEIGHT", "全局粗细微调", "不修改字体文件")
        }
        item {
            Alpha16SystemWeightCard(features)
        }
        item {
            Alpha16Glass(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp),
                shape = RoundedCornerShape(30.dp),
                shadow = 6,
                contentPadding = PaddingValues(16.dp),
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(
                        onClick = onRestoreDefault,
                        enabled = !viewModel.operationBusy && !viewModel.mixState.busy,
                        modifier = Modifier
                            .weight(1f)
                            .height(54.dp),
                        shape = RoundedCornerShape(19.dp),
                    ) { Text("恢复系统字体", fontWeight = FontWeight.Bold) }
                    Button(
                        onClick = viewModel::rebootDevice,
                        enabled = viewModel.rebootRequired &&
                            !viewModel.operationBusy &&
                            !viewModel.mixState.busy,
                        modifier = Modifier
                            .weight(1f)
                            .height(54.dp),
                        shape = RoundedCornerShape(19.dp),
                    ) {
                        Icon(Icons.Rounded.RestartAlt, null)
                        Spacer(Modifier.width(7.dp))
                        Text("立即重启", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun Alpha16OverviewHero(snapshot: ModuleSnapshot) {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val shape = RoundedCornerShape(36.dp)
    val positive = snapshot.installed && snapshot.rootGranted
    Box(
        modifier = Modifier
            .padding(horizontal = 18.dp)
            .fillMaxWidth()
            .shadow(12.dp, shape, clip = false)
            .clip(shape)
            .background(if (dark) scheme.surfaceContainerHigh else scheme.surface)
            .border(
                1.dp,
                scheme.onSurface.copy(alpha = if (dark) .08f else .05f),
                shape,
            )
            .drawBehind {
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(
                            scheme.primary.copy(alpha = if (dark) .20f else .16f),
                            Color.Transparent,
                        ),
                        center = Offset(size.width, 0f),
                        radius = size.width * .78f,
                    ),
                    radius = size.width * .78f,
                    center = Offset(size.width, 0f),
                )
                drawRoundRect(
                    brush = Brush.verticalGradient(
                        listOf(
                            Color.White.copy(alpha = if (dark) .05f else .35f),
                            Color.Transparent,
                        ),
                    ),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(36.dp.toPx()),
                    size = size.copy(height = size.height * .38f),
                )
            }
            .padding(24.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(if (positive) Color(0xFF2DBE87) else Color(0xFFF2A93B)),
                )
                Spacer(Modifier.width(8.dp))
                Text(snapshot.version, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                Text(
                    if (snapshot.installed) "  ·  模块已连接" else "  ·  等待模块",
                    color = scheme.onSurfaceVariant,
                    fontSize = 11.sp,
                )
            }
            Spacer(Modifier.height(23.dp))
            Text(
                "当前字体",
                color = scheme.onSurfaceVariant,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
            )
            Text(
                snapshot.activeLabel,
                color = scheme.onSurface,
                fontSize = 38.sp,
                lineHeight = 43.sp,
                fontWeight = FontWeight.Black,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(20.dp))
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(22.dp))
                    .background(scheme.onSurface.copy(alpha = if (dark) .055f else .04f))
                    .padding(horizontal = 15.dp, vertical = 13.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    if (positive) Icons.Rounded.CheckCircle else Icons.Rounded.Refresh,
                    contentDescription = null,
                    tint = if (positive) Color(0xFF2DBE87) else scheme.primary,
                    modifier = Modifier.size(24.dp),
                )
                Spacer(Modifier.width(11.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (snapshot.taskState == "running") "字体任务执行中" else if (positive) "字体引擎已就绪" else "正在等待连接",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        snapshot.taskMessage,
                        color = scheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (snapshot.loading) {
                    CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                }
            }
        }
    }
}

private data class Alpha16ActionItem(
    val icon: ImageVector,
    val title: String,
    val description: String,
    val onClick: () -> Unit,
)

@Composable
private fun Alpha16ActionGroup(items: List<Alpha16ActionItem>) {
    Alpha16Glass(
        modifier = Modifier
            .padding(horizontal = 18.dp)
            .fillMaxWidth(),
        shape = RoundedCornerShape(34.dp),
        shadow = 8,
        contentPadding = PaddingValues(horizontal = 15.dp, vertical = 5.dp),
    ) {
        Column {
            items.forEachIndexed { index, item ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(22.dp))
                        .clickable(onClick = item.onClick)
                        .padding(vertical = 14.dp, horizontal = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = RoundedCornerShape(17.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                item.icon,
                                null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(25.dp),
                            )
                        }
                    }
                    Spacer(Modifier.width(13.dp))
                    Column(Modifier.weight(1f)) {
                        Text(item.title, fontSize = 17.sp, fontWeight = FontWeight.Black)
                        Text(
                            item.description,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Icon(
                        Icons.Rounded.KeyboardArrowDown,
                        null,
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.rotate(-90f),
                    )
                }
                if (index != items.lastIndex) {
                    HorizontalDivider(
                        Modifier.padding(start = 61.dp),
                        color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f),
                    )
                }
            }
        }
    }
}

@Composable
private fun Alpha16SectionHeader(eyebrow: String, title: String, subtitle: String) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 20.dp, vertical = 3.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                eyebrow,
                color = MaterialTheme.colorScheme.primary,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.sp,
            )
            Text(title, fontSize = 25.sp, fontWeight = FontWeight.Black)
        }
        Text(
            subtitle,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp,
        )
    }
}

@Composable
private fun Alpha16Metric(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    value: String,
) {
    Alpha16Glass(
        modifier = modifier,
        shape = RoundedCornerShape(28.dp),
        shadow = 6,
        contentPadding = PaddingValues(17.dp),
    ) {
        Column {
            Surface(
                modifier = Modifier.size(42.dp),
                shape = RoundedCornerShape(15.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        icon,
                        null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(22.dp),
                    )
                }
            }
            Spacer(Modifier.height(13.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
            Text(
                value,
                fontWeight = FontWeight.Black,
                fontSize = 14.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun Alpha16SystemWeightCard(features: Alpha15FeatureViewModel) {
    val state = features.systemWeight
    Alpha16Glass(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp),
        shape = RoundedCornerShape(34.dp),
        shadow = 8,
        contentPadding = PaddingValues(20.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.Rounded.Speed,
                            null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(27.dp),
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text("全局粗细微调", fontSize = 18.sp, fontWeight = FontWeight.Black)
                    Text(
                        "向左更细，向右更粗",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                    )
                }
                Alpha16Pill(
                    if (state.loading) "读取中" else state.weight.toString(),
                    MaterialTheme.colorScheme.primary,
                )
            }
            Spacer(Modifier.height(18.dp))
            if (state.loading) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
            } else if (!state.supported) {
                Text(
                    state.error.ifBlank { "当前系统不支持全局粗细微调" },
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 12.sp,
                )
            } else {
                Slider(
                    value = state.weight.toFloat(),
                    onValueChange = features::previewSystemWeight,
                    enabled = !state.applying,
                    valueRange = state.min.toFloat()..state.max.toFloat(),
                    steps = (((state.max - state.min) / state.step) - 1).coerceAtLeast(0),
                )
                Row(Modifier.fillMaxWidth()) {
                    Text("更细 ${state.min}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    Spacer(Modifier.weight(1f))
                    Text("标准 400", color = MaterialTheme.colorScheme.primary, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.weight(1f))
                    Text("${state.max} 更粗", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                Spacer(Modifier.height(13.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        state.error.ifBlank { state.message },
                        modifier = Modifier.weight(1f),
                        color = if (state.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        maxLines = 2,
                    )
                    TextButton(
                        onClick = features::resetSystemWeight,
                        enabled = !state.applying,
                    ) { Text("恢复原始") }
                }
            }
        }
    }
}

@Composable
private fun Alpha16LibraryPage(
    viewModel: LuoShuViewModel,
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
            Alpha16Header(
                "FONT LIBRARY",
                "字体库",
                "直接导入、预览和应用",
                { viewModel.refreshFonts(force = true) },
            )
        }
        item {
            Alpha16Glass(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp),
                shape = RoundedCornerShape(24.dp),
                shadow = 6,
                contentPadding = PaddingValues(8.dp),
            ) {
                OutlinedTextField(
                    value = viewModel.searchQuery,
                    onValueChange = viewModel::setSearchQuery,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = RoundedCornerShape(18.dp),
                    leadingIcon = { Icon(Icons.Rounded.Search, null) },
                    placeholder = { Text("搜索字体名称或格式") },
                )
            }
        }
        if (viewModel.fontLoading || viewModel.operationBusy) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        }
        if (viewModel.fontError.isNotBlank()) {
            item { Alpha16Error(viewModel.fontError) }
        }
        if (viewModel.operationMessage.isNotBlank()) {
            item { Alpha16Operation(viewModel) }
        }
        item {
            Alpha16SystemFontCard(
                active = viewModel.snapshot.activeFont == "default",
                busy = viewModel.operationBusy,
                onRestore = onRestoreDefault,
            )
        }
        if (!viewModel.fontLoading && viewModel.filteredFonts.isEmpty()) {
            item {
                Alpha16Glass(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp),
                    shape = RoundedCornerShape(32.dp),
                    contentPadding = PaddingValues(34.dp),
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
            Alpha16FontCard(
                font = font,
                active = viewModel.snapshot.activeFont == font.id,
                busy = viewModel.operationBusy || viewModel.mixState.busy,
                onApply = { onApply(font) },
                onDelete = { onDelete(font) },
            )
        }
    }
}

@Composable
private fun Alpha16SystemFontCard(
    active: Boolean,
    busy: Boolean,
    onRestore: () -> Unit,
) {
    Alpha16Glass(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp),
        shape = RoundedCornerShape(32.dp),
        shadow = 8,
        contentPadding = PaddingValues(18.dp),
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
                Text(
                    "恢复 ROM 原始字体映射",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                )
            }
            if (active) {
                Alpha16Pill("使用中", Color(0xFF2DBE87))
            } else {
                Button(
                    onClick = onRestore,
                    enabled = !busy,
                    shape = RoundedCornerShape(17.dp),
                ) { Text("恢复") }
            }
        }
    }
}

@Composable
private fun Alpha16FontCard(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    Alpha16Glass(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp),
        shape = RoundedCornerShape(34.dp),
        shadow = 8,
        contentPadding = PaddingValues(18.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            "Aa",
                            color = MaterialTheme.colorScheme.primary,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        font.name,
                        fontWeight = FontWeight.Black,
                        fontSize = 16.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        listOf(font.format, font.size, font.date)
                            .filter { it.isNotBlank() }
                            .joinToString(" · "),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) {
                    IconButton(onClick = onDelete, enabled = !busy) {
                        Icon(
                            Icons.Rounded.Delete,
                            contentDescription = "删除",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
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
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(94.dp)
                        .padding(horizontal = 17.dp, vertical = 12.dp),
                    textSizeSp = 24f,
                    maxLines = 2,
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Alpha16Pill(capabilityLabel16(font), MaterialTheme.colorScheme.primary)
                Spacer(Modifier.weight(1f))
                if (active) {
                    Text(
                        "当前使用",
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Black,
                        fontSize = 12.sp,
                    )
                } else {
                    Button(
                        onClick = onApply,
                        enabled = font.valid && !busy,
                        shape = RoundedCornerShape(17.dp),
                    ) { Text("应用字体", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}

@Composable
private fun Alpha16StudioPage(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    onPick: (MixSlot) -> Unit,
) {
    val state = viewModel.mixState
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val direct = directApplyFontId16(state)
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = bottomInset + 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Alpha16Header(
                "FONT STUDIO",
                "字体工作台",
                "真实字形、静态字重与可变轴",
                viewModel::refreshMixConfig,
            )
        }
        if (viewModel.fontLoading || state.loading) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        }
        if (state.error.isNotBlank()) {
            item { Alpha16Error(state.error) }
        }
        if (state.busy || state.taskState == "success") {
            item {
                Alpha16Glass(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 18.dp),
                    shape = RoundedCornerShape(30.dp),
                    shadow = 8,
                    contentPadding = PaddingValues(18.dp),
                ) {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                Icons.Rounded.AutoAwesome,
                                null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                            Spacer(Modifier.width(9.dp))
                            Text(
                                state.message,
                                modifier = Modifier.weight(1f),
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                            )
                            Text(
                                "${state.progress}%",
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.Black,
                            )
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
        item {
            Alpha16SlotCard(
                viewModel,
                MixSlot.Cjk,
                "中文基底",
                "完整中文、符号与回退基底",
                onPick,
            )
        }
        item {
            Alpha16SlotCard(
                viewModel,
                MixSlot.Latin,
                "英文字形",
                "替换拉丁字母轮廓",
                onPick,
            )
        }
        item {
            Alpha16SlotCard(
                viewModel,
                MixSlot.Digit,
                "数字字形",
                "替换数字与相关标点",
                onPick,
            )
        }
        item {
            Alpha16CoverageCard(viewModel, features)
        }
        item {
            Alpha16Glass(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp),
                shape = RoundedCornerShape(34.dp),
                shadow = 8,
                contentPadding = PaddingValues(20.dp),
            ) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            modifier = Modifier.size(48.dp),
                            shape = RoundedCornerShape(17.dp),
                            color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Icon(
                                    if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome,
                                    null,
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                        Spacer(Modifier.width(13.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                if (direct != null) "同一字体，无需复合" else "生成完整复合字体",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Black,
                            )
                            Text(
                                if (direct != null) {
                                    "三个槽位均为标准 Regular 400，将直接应用原始字体。"
                                } else {
                                    "当前字重和设计轴会写入最终字体。"
                                },
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 11.sp,
                            )
                        }
                    }
                    Spacer(Modifier.height(18.dp))
                    Button(
                        onClick = {
                            if (direct != null) viewModel.applyFont(direct) else viewModel.startMix()
                        },
                        enabled = !state.busy &&
                            !viewModel.operationBusy &&
                            viewModel.fonts.isNotEmpty(),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(60.dp),
                        shape = RoundedCornerShape(22.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.primary,
                        ),
                    ) {
                        Icon(
                            if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome,
                            null,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (direct != null) "直接应用此字体" else "生成并应用到系统",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "设计轴拖动只更新 App 内预览；应用系统字体后仍建议完整重启。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

@Composable
private fun Alpha16SlotCard(
    viewModel: LuoShuViewModel,
    slot: MixSlot,
    title: String,
    subtitle: String,
    onPick: (MixSlot) -> Unit,
) {
    val state = viewModel.mixState
    val fontId = selectedFontId16(state, slot)
    val font = viewModel.fonts.firstOrNull { it.id == fontId }
    val weight = selectedWeight16(state, slot)
    val axes = selectedAxes16(state, slot)
    Alpha16Glass(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp),
        shape = RoundedCornerShape(34.dp),
        shadow = 8,
        contentPadding = PaddingValues(18.dp),
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
                    Text(
                        subtitle,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
                Alpha16Pill(
                    font?.let(::capabilityLabel16) ?: "未选择",
                    MaterialTheme.colorScheme.primary,
                )
            }
            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(22.dp))
                    .clickable(enabled = !state.busy) { onPick(slot) },
                shape = RoundedCornerShape(22.dp),
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = .035f),
            ) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(15.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
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
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = .028f),
                ) {
                    NativeFontPreview(
                        font = font,
                        text = when (slot) {
                            MixSlot.Cjk -> "洛书中文  Aa  0123"
                            MixSlot.Latin -> "LuoShu Typography 0123"
                            MixSlot.Digit -> "0123456789 Aa"
                        },
                        axes = axes,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(74.dp)
                            .padding(horizontal = 14.dp),
                        textSizeSp = 25f,
                        gravity = Gravity.CENTER,
                        maxLines = 1,
                    )
                }
                Spacer(Modifier.height(14.dp))
                Alpha16WeightControl(
                    font = font,
                    value = weight,
                    axes = axes,
                    enabled = !state.busy,
                    onValue = { viewModel.updateMixWeight(slot, it) },
                    onAxis = { tag, axisValue ->
                        viewModel.updateMixAxis(slot, tag, axisValue)
                    },
                )
            }
        }
    }
}

@Composable
private fun Alpha16WeightControl(
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
                Text(
                    "正在读取真实可变轴…",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                )
            }
        }
        font.variable && axisInfo.axes.isNotEmpty() -> {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                val weightAxis = axisInfo.axes.firstOrNull { it.tag == "wght" }
                if (weightAxis != null) {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Alpha16ChoiceChip(
                            text = "原始默认 ${axisValueLabel16(weightAxis.default)}",
                            selected = abs((axes["wght"] ?: weightAxis.default) - weightAxis.default) < .5f,
                            enabled = enabled,
                        ) { onAxis("wght", weightAxis.default) }
                        Alpha16ChoiceChip(
                            text = "Regular 400",
                            selected = abs((axes["wght"] ?: weightAxis.default) - 400f) < .5f,
                            enabled = enabled && 400f in weightAxis.min..weightAxis.max,
                        ) { onAxis("wght", 400f.coerceIn(weightAxis.min, weightAxis.max)) }
                    }
                    Text(
                        "字体原始默认 ${axisValueLabel16(weightAxis.default)} · 系统常规基准 400 · 当前 ${axisValueLabel16(axes["wght"] ?: weightAxis.default)}",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
                axisInfo.axes.forEach { axis ->
                    val minimum = axis.min.coerceAtMost(axis.max)
                    val maximum = axis.max.coerceAtLeast(axis.min)
                    val current = (axes[axis.tag] ?: axis.default).coerceIn(minimum, maximum)
                    val isWeight = axis.tag == "wght"
                    val stepCount = if (isWeight && maximum > minimum) {
                        (((maximum - minimum) / 10f).roundToInt() - 1).coerceAtLeast(0)
                    } else {
                        0
                    }
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                "${axis.tag} · ${axisDisplayName16(axis.tag)}",
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp,
                            )
                            Spacer(Modifier.weight(1f))
                            Text(
                                axisValueLabel16(current),
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.Black,
                            )
                        }
                        Slider(
                            value = current,
                            onValueChange = { raw ->
                                val next = if (isWeight) {
                                    ((raw / 10f).roundToInt() * 10).toFloat()
                                        .coerceIn(minimum, maximum)
                                } else {
                                    raw.coerceIn(minimum, maximum)
                                }
                                onAxis(axis.tag, next)
                            },
                            enabled = enabled,
                            valueRange = minimum..maximum,
                            steps = stepCount,
                        )
                        Text(
                            "${axisValueLabel16(minimum)} · 原始默认 ${axisValueLabel16(axis.default)} · ${axisValueLabel16(maximum)}",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 9.sp,
                        )
                    }
                }
            }
        }
        font.variable -> {
            Text(
                axisInfo.error.ifBlank { "该字体没有可用的 fvar 轴" },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
            )
        }
        staticWeights16(font).size >= 2 -> {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("真实静态字重", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Spacer(Modifier.weight(1f))
                    Text(
                        value.toString(),
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Black,
                    )
                }
                Spacer(Modifier.height(10.dp))
                Row(
                    Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    staticWeights16(font).forEach { option ->
                        Alpha16ChoiceChip(
                            text = weightName16(option),
                            selected = option == value,
                            enabled = enabled,
                        ) { onValue(option) }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    "切换档位会加载该字体族对应的真实文件。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                )
            }
        }
        else -> {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("固定字重", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text(
                        "该字体没有可调轴，也没有其他静态字重文件。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
                Alpha16Pill(weightName16(fixedWeight16(font)), MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun Alpha16ChoiceChip(
    text: String,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .clip(RoundedCornerShape(999.dp))
            .clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (selected) {
            MaterialTheme.colorScheme.primary
        } else {
            MaterialTheme.colorScheme.onSurface.copy(alpha = .045f)
        },
        border = BorderStroke(
            1.dp,
            if (selected) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.outline.copy(alpha = .18f),
        ),
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp),
            color = if (selected) MaterialTheme.colorScheme.onPrimary
            else MaterialTheme.colorScheme.onSurface,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun Alpha16CoverageCard(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
) {
    val fontId = viewModel.mixState.cjk
    val font = viewModel.fonts.firstOrNull { it.id == fontId }
    val probe = features.coverage
    Alpha16Glass(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp),
        shape = RoundedCornerShape(34.dp),
        shadow = 8,
        contentPadding = PaddingValues(20.dp),
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = RoundedCornerShape(17.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.Rounded.Search,
                            null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
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
                    if (probe.loading) {
                        CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    } else {
                        Text("检测")
                    }
                }
            }
            val metrics = probe.metrics.takeIf { probe.fontId == fontId }
            if (metrics != null) {
                Spacer(Modifier.height(16.dp))
                Alpha16CoverageRow("中文", metrics.cjkRatio)
                Alpha16CoverageRow("英文", metrics.latinRatio)
                Alpha16CoverageRow("数字", metrics.digitRatio)
                Alpha16CoverageRow("标点", metrics.punctuationRatio)
                if (metrics.missingSample.isNotBlank()) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "缺失示例：${metrics.missingSample}",
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 10.sp,
                    )
                }
            } else if (probe.error.isNotBlank() && probe.fontId == fontId) {
                Spacer(Modifier.height(12.dp))
                Text(probe.error, color = MaterialTheme.colorScheme.error, fontSize = 11.sp)
            } else {
                Spacer(Modifier.height(12.dp))
                Text(
                    "用于判断局部字体不一致是否由缺字 fallback 引起。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                )
            }
        }
    }
}

@Composable
private fun Alpha16CoverageRow(label: String, ratio: Float) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, modifier = Modifier.width(42.dp), fontSize = 11.sp, fontWeight = FontWeight.Bold)
        LinearProgressIndicator(
            progress = { ratio },
            modifier = Modifier
                .weight(1f)
                .height(7.dp)
                .clip(RoundedCornerShape(999.dp)),
        )
        Spacer(Modifier.width(10.dp))
        Text(
            "${(ratio * 100).roundToInt()}%",
            color = MaterialTheme.colorScheme.primary,
            fontSize = 11.sp,
            fontWeight = FontWeight.Black,
        )
    }
}

@Composable
private fun Alpha16LogsPage(
    logs: String,
    onRefresh: () -> Unit,
) {
    val bottomInset = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    Column(Modifier.fillMaxSize()) {
        Alpha16Header("DIAGNOSTICS", "运行日志", "字体任务与错误记录", onRefresh)
        Alpha16Glass(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 18.dp)
                .padding(bottom = bottomInset + 106.dp),
            shape = RoundedCornerShape(34.dp),
            shadow = 8,
            contentPadding = PaddingValues(18.dp),
        ) {
            SelectionContainer {
                Text(
                    logs,
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState()),
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
private fun Alpha16FontPicker(
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
                Modifier
                    .fillMaxWidth()
                    .heightIn(max = 470.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(fonts, key = { it.id }) { font ->
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(20.dp))
                            .clickable { onChoose(font) },
                        shape = RoundedCornerShape(20.dp),
                        color = if (font.id == selected) {
                            MaterialTheme.colorScheme.primary.copy(alpha = .12f)
                        } else {
                            MaterialTheme.colorScheme.surfaceVariant.copy(alpha = .54f)
                        },
                    ) {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    font.name,
                                    fontWeight = FontWeight.Bold,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    capabilityLabel16(font),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontSize = 10.sp,
                                )
                            }
                            if (font.id == selected) {
                                Icon(
                                    Icons.Rounded.CheckCircle,
                                    null,
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        },
    )
}

@Composable
private fun Alpha16Operation(
    viewModel: LuoShuViewModel,
    modifier: Modifier = Modifier
        .fillMaxWidth()
        .padding(horizontal = 18.dp),
) {
    Alpha16Glass(
        modifier = modifier,
        shape = RoundedCornerShape(25.dp),
        shadow = 5,
        contentPadding = PaddingValues(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (viewModel.operationBusy) {
                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            } else {
                Icon(
                    Icons.Rounded.CheckCircle,
                    null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
            Spacer(Modifier.width(10.dp))
            Text(viewModel.operationMessage, modifier = Modifier.weight(1f), fontSize = 12.sp)
        }
    }
}

@Composable
private fun Alpha16Error(
    message: String,
    modifier: Modifier = Modifier
        .fillMaxWidth()
        .padding(horizontal = 18.dp),
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(25.dp),
        color = MaterialTheme.colorScheme.errorContainer.copy(alpha = .88f),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Rounded.Warning,
                null,
                tint = MaterialTheme.colorScheme.error,
            )
            Spacer(Modifier.width(10.dp))
            Text(
                message,
                modifier = Modifier.weight(1f),
                color = MaterialTheme.colorScheme.onErrorContainer,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun Alpha16Pill(text: String, color: Color) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = color.copy(alpha = .12f),
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
        )
    }
}

private fun selectedFontId16(state: MixState, slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> state.cjk
    MixSlot.Latin -> state.latin
    MixSlot.Digit -> state.digit
}

private fun selectedWeight16(state: MixState, slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> state.cjkWeight
    MixSlot.Latin -> state.latinWeight
    MixSlot.Digit -> state.digitWeight
}

private fun selectedAxes16(state: MixState, slot: MixSlot): Map<String, Float> = when (slot) {
    MixSlot.Cjk -> state.cjkAxes
    MixSlot.Latin -> state.latinAxes
    MixSlot.Digit -> state.digitAxes
}

private fun directApplyFontId16(state: MixState): String? {
    val ids = listOf(state.cjk, state.latin, state.digit)
    if (ids.any { it.isBlank() } || ids.distinct().size != 1) return null
    if (listOf(state.cjkWeight, state.latinWeight, state.digitWeight).any { it != 400 }) return null
    val allAxes = listOf(state.cjkAxes, state.latinAxes, state.digitAxes)
    val standard = allAxes.all { axes ->
        axes.all { (tag, value) -> tag == "wght" && abs(value - 400f) < .5f }
    }
    return ids.first().takeIf { standard }
}

private fun staticWeights16(font: FontItem): List<Int> = font.weights
    .filterNot { it == "variable" }
    .map(::roleWeight16)
    .distinct()
    .sorted()

private fun fixedWeight16(font: FontItem): Int = staticWeights16(font).firstOrNull() ?: 400

private fun normalizedWeight16(font: FontItem, current: Int): Int = when {
    font.variable -> current.coerceIn(100, 900)
    staticWeights16(font).size >= 2 ->
        staticWeights16(font).minByOrNull { abs(it - current) } ?: 400
    else -> fixedWeight16(font)
}

private fun capabilityLabel16(font: FontItem): String = when {
    font.variable -> "可变字体"
    staticWeights16(font).size >= 2 -> "${staticWeights16(font).size} 档静态字重"
    else -> "固定 ${weightName16(fixedWeight16(font))}"
}

private fun roleWeight16(role: String): Int = when (role.lowercase()) {
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

private fun weightName16(weight: Int): String = when (weight) {
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

private fun axisDisplayName16(tag: String): String = when (tag) {
    "wght" -> "字重"
    "wdth" -> "字宽"
    "opsz" -> "光学尺寸"
    "slnt" -> "倾斜"
    "ital" -> "斜体"
    "GRAD" -> "笔画等级"
    else -> "设计轴"
}

private fun axisValueLabel16(value: Float): String =
    if (value % 1f == 0f) value.roundToInt().toString()
    else value.toString().trimEnd('0').trimEnd('.')
