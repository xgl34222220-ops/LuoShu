package io.github.xgl34222220.luoshu

import android.view.Gravity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.weight
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
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.List
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Speed
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
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.roundToInt

private enum class Alpha15Page(val label: String, val subtitle: String, val icon: ImageVector) {
    Home("概览", "系统状态", Icons.Rounded.Home),
    Library("字体库", "导入与应用", Icons.Rounded.List),
    Studio("工作台", "字形与轴", Icons.Rounded.Layers),
    Logs("日志", "任务诊断", Icons.Rounded.Description),
}

private val Alpha15Light = lightColorScheme(
    primary = Color(0xFF426FE8),
    onPrimary = Color.White,
    secondary = Color(0xFF7159D9),
    background = Color(0xFFF5F6FB),
    surface = Color.White,
    surfaceVariant = Color(0xFFF0F2F8),
    onSurface = Color(0xFF171923),
    onSurfaceVariant = Color(0xFF686C7B),
)

private val Alpha15Dark = darkColorScheme(
    primary = Color(0xFFB7C8FF),
    onPrimary = Color(0xFF17336C),
    secondary = Color(0xFFD1C2FF),
    background = Color(0xFF101117),
    surface = Color(0xFF1A1C24),
    surfaceVariant = Color(0xFF272A34),
    onSurface = Color(0xFFF3F3F7),
    onSurfaceVariant = Color(0xFFB8BAC5),
)

@Composable
internal fun LuoShuAlpha15App(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
) {
    var page by rememberSaveable { mutableStateOf(Alpha15Page.Home) }
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
            Alpha15Page.Home -> features.refreshSystemWeight()
            Alpha15Page.Library -> viewModel.ensureFonts()
            Alpha15Page.Studio -> {
                viewModel.ensureFonts()
                viewModel.refreshMixConfig()
            }
            Alpha15Page.Logs -> viewModel.refreshLogs()
        }
    }
    BackHandler(enabled = page != Alpha15Page.Home) { page = Alpha15Page.Home }

    MaterialTheme(
        colorScheme = if (androidx.compose.foundation.isSystemInDarkTheme()) Alpha15Dark else Alpha15Light,
    ) {
        Box(Modifier.fillMaxSize()) {
            Alpha15Backdrop()
            Scaffold(
                modifier = Modifier.fillMaxSize(),
                containerColor = Color.Transparent,
                bottomBar = {
                    Alpha15Dock(
                        current = page,
                        onSelect = { page = it },
                    )
                },
            ) { padding ->
                when (page) {
                    Alpha15Page.Home -> Alpha15HomePage(
                        viewModel = viewModel,
                        features = features,
                        onOpenLibrary = { page = Alpha15Page.Library },
                        onOpenStudio = { page = Alpha15Page.Studio },
                        onRestoreDefault = { restoreDefault = true },
                        modifier = Modifier.padding(padding),
                    )
                    Alpha15Page.Library -> Alpha15LibraryPage(
                        viewModel = viewModel,
                        onApply = { pendingApply = it },
                        onDelete = { pendingDelete = it },
                        onRestoreDefault = { restoreDefault = true },
                        modifier = Modifier.padding(padding),
                    )
                    Alpha15Page.Studio -> Alpha15StudioPage(
                        viewModel = viewModel,
                        features = features,
                        onPick = { pickerSlot = it },
                        modifier = Modifier.padding(padding),
                    )
                    Alpha15Page.Logs -> Alpha15LogsPage(
                        logs = viewModel.logs,
                        onRefresh = viewModel::refreshLogs,
                        modifier = Modifier.padding(padding),
                    )
                }
            }
        }

        pendingApply?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingApply = null },
                title = { Text("应用字体", fontWeight = FontWeight.Black) },
                text = { Text("直接应用「${font.name}」。字体文件准备完成后需要完整重启手机。") },
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
                text = { Text("恢复 ROM 自带字体映射。完成后需要完整重启手机。系统粗细微调可单独恢复。") },
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
            Alpha15FontPicker(
                slot = slot,
                fonts = viewModel.fonts.filter { it.valid },
                selected = selectedFontId15(viewModel.mixState, slot),
                onDismiss = { pickerSlot = null },
                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(slot, normalizedWeight15(font, selectedWeight15(viewModel.mixState, slot)))
                    pickerSlot = null
                },
            )
        }
    }
}

@Composable
private fun Alpha15Backdrop() {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    val base = if (dark) {
        Brush.verticalGradient(listOf(Color(0xFF101117), Color(0xFF171827), Color(0xFF101117)))
    } else {
        Brush.verticalGradient(listOf(Color(0xFFFAF9FF), Color(0xFFF1F5FF), Color(0xFFF8F8FC)))
    }
    Box(Modifier.fillMaxSize().background(base)) {
        Box(
            Modifier
                .offset(x = 220.dp, y = (-80).dp)
                .size(320.dp)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFF7864FF).copy(alpha = if (dark) 0.25f else 0.22f), Color.Transparent),
                    ),
                    CircleShape,
                ),
        )
        Box(
            Modifier
                .offset(x = (-130).dp, y = 410.dp)
                .size(350.dp)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFF48A8FF).copy(alpha = if (dark) 0.19f else 0.17f), Color.Transparent),
                    ),
                    CircleShape,
                ),
        )
        Box(
            Modifier
                .offset(x = 230.dp, y = 820.dp)
                .size(280.dp)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFFFF92D0).copy(alpha = 0.11f), Color.Transparent),
                    ),
                    CircleShape,
                ),
        )
    }
}

@Composable
private fun Alpha15Dock(current: Alpha15Page, onSelect: (Alpha15Page) -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .navigationBarsPadding()
            .padding(horizontal = 18.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Alpha15Glass(Modifier.fillMaxWidth(), RoundedCornerShape(32.dp), 18.dp) {
            Row(Modifier.fillMaxWidth().padding(7.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Alpha15Page.entries.forEach { page ->
                    val selected = current == page
                    Row(
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(24.dp))
                            .background(
                                if (selected) {
                                    Brush.horizontalGradient(
                                        listOf(
                                            Color(0xFF4F75F2).copy(alpha = 0.18f),
                                            Color(0xFF8C5FE6).copy(alpha = 0.15f),
                                        ),
                                    )
                                } else {
                                    Brush.linearGradient(listOf(Color.Transparent, Color.Transparent))
                                },
                            )
                            .clickable { onSelect(page) }
                            .padding(vertical = 10.dp),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            page.icon,
                            contentDescription = page.label,
                            modifier = Modifier.size(21.dp),
                            tint = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (selected) {
                            Spacer(Modifier.width(7.dp))
                            Text(page.label, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Alpha15Header(
    eyebrow: String,
    title: String,
    subtitle: String,
    onRefresh: (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 22.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(eyebrow.uppercase(), color = MaterialTheme.colorScheme.primary, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp)
            Text(title, fontSize = 30.sp, lineHeight = 34.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
        onRefresh?.let {
            Alpha15Glass(shape = RoundedCornerShape(18.dp), shadow = 6.dp) {
                IconButton(onClick = it) { Icon(Icons.Rounded.Refresh, contentDescription = "刷新") }
            }
        }
    }
}

@Composable
private fun Alpha15HomePage(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    onOpenLibrary: () -> Unit,
    onOpenStudio: () -> Unit,
    onRestoreDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val snapshot = viewModel.snapshot
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(13.dp),
    ) {
        item { Alpha15Header("LUOSHU ALPHA1.5", "洛书", "系统粗细与字体设计轴已分离", viewModel::refresh) }
        item {
            Surface(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                shape = RoundedCornerShape(36.dp),
                color = Color.Transparent,
                shadowElevation = 18.dp,
            ) {
                Column(
                    Modifier
                        .background(Brush.linearGradient(listOf(Color(0xFF4F72EF), Color(0xFF705CE2), Color(0xFF9057CF))))
                        .padding(24.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            modifier = Modifier.size(64.dp),
                            shape = RoundedCornerShape(22.dp),
                            color = Color.White.copy(alpha = 0.18f),
                            border = BorderStroke(1.dp, Color.White.copy(alpha = 0.32f)),
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text("洛", color = Color.White, fontSize = 28.sp, fontWeight = FontWeight.Black)
                            }
                        }
                        Spacer(Modifier.width(16.dp))
                        Column(Modifier.weight(1f)) {
                            Text(snapshot.version, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Black)
                            Text(
                                if (snapshot.installed) "${snapshot.rootManager} · ${snapshot.mountEngine}" else "等待连接匹配模块",
                                color = Color.White.copy(alpha = 0.78f),
                                fontSize = 11.sp,
                            )
                        }
                        if (snapshot.loading) CircularProgressIndicator(Modifier.size(24.dp), color = Color.White, strokeWidth = 2.5.dp)
                        else Icon(
                            if (snapshot.installed) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                            contentDescription = null,
                            tint = Color.White,
                        )
                    }
                    Spacer(Modifier.height(24.dp))
                    Text("当前系统字体", color = Color.White.copy(alpha = 0.68f), fontSize = 10.sp)
                    Text(snapshot.activeLabel, color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Black)
                    Spacer(Modifier.height(5.dp))
                    Text(snapshot.taskMessage, color = Color.White.copy(alpha = 0.78f), fontSize = 11.sp, maxLines = 2)
                }
            }
        }
        if (snapshot.error.isNotBlank()) item { Alpha15Error(snapshot.error) }
        if (viewModel.operationMessage.isNotBlank()) item { Alpha15Operation(viewModel) }
        item { Alpha15SystemWeightCard(features) }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.spacedBy(11.dp),
            ) {
                Alpha15ActionCard(Modifier.weight(1f), "字体库", "直接导入与应用", Icons.Rounded.List, onOpenLibrary)
                Alpha15ActionCard(Modifier.weight(1f), "字体工作台", "组合、轴与覆盖诊断", Icons.Rounded.AutoAwesome, onOpenStudio)
            }
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.spacedBy(11.dp),
            ) {
                Alpha15MiniStatus(Modifier.weight(1f), Icons.Rounded.Security, "Root", if (snapshot.rootGranted) snapshot.rootManager else "未授权")
                Alpha15MiniStatus(Modifier.weight(1f), Icons.Rounded.Speed, "系统粗细", features.systemWeight.weight.toString())
            }
        }
        item {
            Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(28.dp)) {
                Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(
                        onClick = onRestoreDefault,
                        enabled = !viewModel.operationBusy && !viewModel.mixState.busy,
                        modifier = Modifier.weight(1f).height(50.dp),
                        shape = RoundedCornerShape(17.dp),
                    ) { Text("恢复系统字体") }
                    Button(
                        onClick = viewModel::rebootDevice,
                        enabled = viewModel.rebootRequired && !viewModel.operationBusy && !viewModel.mixState.busy,
                        modifier = Modifier.weight(1f).height(50.dp),
                        shape = RoundedCornerShape(17.dp),
                    ) {
                        Icon(Icons.Rounded.RestartAlt, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("立即重启")
                    }
                }
            }
        }
    }
}

@Composable
private fun Alpha15SystemWeightCard(features: Alpha15FeatureViewModel) {
    val state = features.systemWeight
    Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(32.dp), 14.dp) {
        Column(Modifier.fillMaxWidth().padding(19.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(Modifier.size(47.dp), RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.Speed, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("系统全局粗细微调", fontSize = 17.sp, fontWeight = FontWeight.Black)
                    Text("Android 字重偏移 · 与字体文件的 wght 轴不是同一件事", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                if (state.loading || state.applying) CircularProgressIndicator(Modifier.size(23.dp), strokeWidth = 2.3.dp)
                else Alpha15Pill(if (state.supported) "可即时写入" else "不支持", if (state.supported) Color(0xFF3E7CF2) else MaterialTheme.colorScheme.error)
            }
            Spacer(Modifier.height(16.dp))
            if (state.supported) {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(state.weight.toString(), fontSize = 34.sp, fontWeight = FontWeight.Black, color = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(7.dp))
                    Text(
                        if (state.adjustment >= 0) "Regular 400  +${state.adjustment}" else "Regular 400  ${state.adjustment}",
                        modifier = Modifier.padding(bottom = 6.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                    )
                }
                Slider(
                    value = state.weight.toFloat(),
                    onValueChange = features::previewSystemWeight,
                    enabled = !state.loading && !state.applying,
                    valueRange = state.min.toFloat()..state.max.toFloat(),
                    steps = (((state.max - state.min) / state.step) - 1).coerceAtLeast(0),
                )
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(300, 400, 500, 600, 700).filter { it in state.min..state.max }.forEach { weight ->
                        Alpha15ChoiceChip(
                            text = if (weight == 400) "400 · 标准" else weight.toString(),
                            selected = state.weight == weight,
                            enabled = !state.applying,
                            onClick = { features.commitSystemWeight(weight) },
                        )
                    }
                }
                Spacer(Modifier.height(13.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        state.error.ifBlank { state.message },
                        modifier = Modifier.weight(1f),
                        color = if (state.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        lineHeight = 15.sp,
                    )
                    TextButton(onClick = features::resetSystemWeight, enabled = !state.applying) { Text("恢复原始") }
                }
            } else {
                Text(
                    state.error.ifBlank { "当前 ROM 没有暴露安全的系统字体粗细接口。字体工作台中的真实轴预览仍可正常使用。" },
                    color = if (state.error.isNotBlank()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    lineHeight = 17.sp,
                )
            }
        }
    }
}

@Composable
private fun Alpha15LibraryPage(
    viewModel: LuoShuViewModel,
    onApply: (FontItem) -> Unit,
    onDelete: (FontItem) -> Unit,
    onRestoreDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxSize()) {
        Alpha15Header("FONT LIBRARY", "字体库", "直接字体文件优先 · 模块 ZIP 为高级导入", { viewModel.refreshFonts(force = true) })
        Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(24.dp)) {
            OutlinedTextField(
                value = viewModel.searchQuery,
                onValueChange = viewModel::setSearchQuery,
                modifier = Modifier.fillMaxWidth().padding(8.dp),
                singleLine = true,
                shape = RoundedCornerShape(18.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索字体名称或格式") },
            )
        }
        if (viewModel.fontLoading || viewModel.operationBusy) {
            LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 18.dp, vertical = 13.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Alpha15Glass(Modifier.fillMaxWidth(), RoundedCornerShape(27.dp)) {
                    Column(Modifier.fillMaxWidth().padding(17.dp)) {
                        Text("导入建议", fontWeight = FontWeight.Black)
                        Text(
                            "优先使用右下角导入按钮选择 TTF、OTF 或 TTC，识别最准确。字体模块 ZIP 仍然保留，但作为高级入口自动提取，不要求普通用户自己寻找 system/fonts。",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                            lineHeight = 16.sp,
                        )
                    }
                }
            }
            if (viewModel.fontError.isNotBlank()) item { Alpha15Error(viewModel.fontError, Modifier.fillMaxWidth()) }
            if (viewModel.operationMessage.isNotBlank()) item { Alpha15Operation(viewModel, Modifier.fillMaxWidth()) }
            item { Alpha15SystemFontCard(viewModel.snapshot.activeFont == "default", viewModel.operationBusy, onRestoreDefault) }
            if (!viewModel.fontLoading && viewModel.filteredFonts.isEmpty()) {
                item {
                    Alpha15Glass(Modifier.fillMaxWidth(), RoundedCornerShape(30.dp)) {
                        Column(Modifier.fillMaxWidth().padding(34.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("没有找到字体", fontSize = 19.sp, fontWeight = FontWeight.Black)
                            Text("点击右下角按钮导入字体文件", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                        }
                    }
                }
            }
            items(viewModel.filteredFonts, key = { it.id }) { font ->
                Alpha15FontCard(
                    font = font,
                    active = viewModel.snapshot.activeFont == font.id,
                    busy = viewModel.operationBusy || viewModel.mixState.busy,
                    onApply = { onApply(font) },
                    onDelete = { onDelete(font) },
                )
            }
        }
    }
}

@Composable
private fun Alpha15SystemFontCard(active: Boolean, busy: Boolean, onRestoreDefault: () -> Unit) {
    Alpha15Glass(Modifier.fillMaxWidth(), RoundedCornerShape(30.dp)) {
        Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(Modifier.size(54.dp), RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
                Box(contentAlignment = Alignment.Center) { Text("系", fontSize = 20.sp, fontWeight = FontWeight.Black) }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", fontSize = 17.sp, fontWeight = FontWeight.Black)
                Text("恢复 ROM 原始字体映射", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
            if (active) Alpha15Pill("使用中", Color(0xFF3F7DF5))
            else Button(onClick = onRestoreDefault, enabled = !busy, shape = RoundedCornerShape(15.dp)) { Text("恢复") }
        }
    }
}

@Composable
private fun Alpha15FontCard(font: FontItem, active: Boolean, busy: Boolean, onApply: () -> Unit, onDelete: () -> Unit) {
    Alpha15Glass(Modifier.fillMaxWidth(), RoundedCornerShape(32.dp), 12.dp) {
        Column(Modifier.fillMaxWidth().padding(17.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = alpha15Accent(font.id).copy(alpha = 0.14f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = alpha15Accent(font.id), fontSize = 17.sp, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(font.name, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) IconButton(onClick = onDelete, enabled = !busy) {
                    Icon(Icons.Rounded.Delete, contentDescription = "删除", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(24.dp),
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.58f),
                border = BorderStroke(1.dp, Color.White.copy(alpha = 0.44f)),
            ) {
                NativeFontPreview(
                    font = font,
                    text = "洛书字体预览\nHello 0123456789",
                    modifier = Modifier.fillMaxWidth().height(94.dp).padding(horizontal = 17.dp, vertical = 12.dp),
                    textSizeSp = 24f,
                    maxLines = 2,
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Alpha15Pill(capabilityLabel15(font), alpha15Accent(font.id))
                Spacer(Modifier.weight(1f))
                if (active) {
                    Text("当前使用", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black, fontSize = 12.sp)
                } else {
                    Button(onClick = onApply, enabled = font.valid && !busy, shape = RoundedCornerShape(16.dp)) {
                        Text("直接应用", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun Alpha15StudioPage(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    onPick: (MixSlot) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state = viewModel.mixState
    val directFont = directApplyCandidate15(state, viewModel.fonts)
    val sameFont = state.cjk.isNotBlank() && state.cjk == state.latin && state.latin == state.digit

    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(13.dp),
    ) {
        item { Alpha15Header("FONT STUDIO", "字体工作台", "原始默认、系统 Regular 和当前参数分别显示", viewModel::refreshMixConfig) }
        if (viewModel.fontLoading || state.loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        if (state.error.isNotBlank()) item { Alpha15Error(state.error) }
        if (viewModel.operationMessage.isNotBlank()) item { Alpha15Operation(viewModel) }
        if (state.busy || state.taskState == "success") {
            item {
                Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(28.dp)) {
                    Column(Modifier.fillMaxWidth().padding(18.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            Spacer(Modifier.width(9.dp))
                            Text(state.message, modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Text("${state.progress}%", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                        Spacer(Modifier.height(12.dp))
                        LinearProgressIndicator(progress = { state.progress / 100f }, modifier = Modifier.fillMaxWidth())
                    }
                }
            }
        }
        item {
            Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(27.dp)) {
                Row(Modifier.fillMaxWidth().padding(17.dp), verticalAlignment = Alignment.CenterVertically) {
                    Surface(Modifier.size(43.dp), RoundedCornerShape(15.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)) {
                        Box(contentAlignment = Alignment.Center) { Icon(Icons.Rounded.TextFields, contentDescription = null, tint = MaterialTheme.colorScheme.primary) }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            when {
                                directFont != null -> "同一字体 · 可直接应用"
                                sameFont -> "同一字体 · 存在自定义轴参数"
                                else -> "多字体组合模式"
                            },
                            fontWeight = FontWeight.Black,
                        )
                        Text(
                            when {
                                directFont != null -> "三个槽位均为标准 Regular 400，不再执行无意义的复合生成。"
                                sameFont -> "轴参数不是标准基准，为保证最终效果仍会实例化并生成。"
                                else -> "中文、英文和数字来自不同字体，需要生成复合字体。"
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                            lineHeight = 15.sp,
                        )
                    }
                    Alpha15Pill(if (directFont != null) "直应用" else "生成", if (directFont != null) Color(0xFF2F8B66) else Color(0xFF775BDD))
                }
            }
        }
        item { Alpha15MixSlotCard(viewModel, features, MixSlot.Cjk, "中文基底", "完整保留中文、符号与 fallback", onPick) }
        item { Alpha15MixSlotCard(viewModel, features, MixSlot.Latin, "英文字形", "替换拉丁字母轮廓", onPick) }
        item { Alpha15MixSlotCard(viewModel, features, MixSlot.Digit, "数字字形", "替换数字与相关标点", onPick) }
        item {
            Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(30.dp)) {
                Column(Modifier.fillMaxWidth().padding(18.dp)) {
                    Text("应用逻辑", fontWeight = FontWeight.Black)
                    Text(
                        if (directFont != null) {
                            "当前三个槽位使用同一个字体且没有自定义设计轴，点击后直接走字体切换链路。"
                        } else {
                            "预览始终实时；点击后才实例化轴参数并写入模块。系统界面通常仍需要完整重启。"
                        },
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        lineHeight = 17.sp,
                    )
                    Spacer(Modifier.height(15.dp))
                    Button(
                        onClick = {
                            if (directFont != null) viewModel.applyFont(directFont.id) else viewModel.startMix()
                        },
                        enabled = !state.busy && !viewModel.operationBusy && viewModel.fonts.isNotEmpty(),
                        modifier = Modifier.fillMaxWidth().height(56.dp),
                        shape = RoundedCornerShape(19.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = if (directFont != null) Color(0xFF347D68) else Color(0xFF4679F5)),
                    ) {
                        Icon(if (directFont != null) Icons.Rounded.CheckCircle else Icons.Rounded.AutoAwesome, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text(if (directFont != null) "直接应用此字体" else "生成并应用到系统", fontWeight = FontWeight.Black)
                    }
                }
            }
        }
    }
}

@Composable
private fun Alpha15MixSlotCard(
    viewModel: LuoShuViewModel,
    features: Alpha15FeatureViewModel,
    slot: MixSlot,
    title: String,
    subtitle: String,
    onPick: (MixSlot) -> Unit,
) {
    val state = viewModel.mixState
    val fontId = selectedFontId15(state, slot)
    val font = viewModel.fonts.firstOrNull { it.id == fontId }
    val weight = selectedWeight15(state, slot)
    val axes = selectedAxes15(state, slot)

    Alpha15Glass(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(32.dp), 12.dp) {
        Column(Modifier.fillMaxWidth().padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(Modifier.size(46.dp), RoundedCornerShape(16.dp), color = alpha15Accent(title).copy(alpha = 0.14f)) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            if (slot == MixSlot.Cjk) "中" else if (slot == MixSlot.Latin) "Aa" else "123",
                            color = alpha15Accent(title),
                            fontWeight = FontWeight.Black,
                        )
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, fontWeight = FontWeight.Black, fontSize = 17.sp)
                    Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                Alpha15Pill(font?.let(::capabilityLabel15) ?: "未选择", alpha15Accent(title))
            }
            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).clickable(enabled = !state.busy) { onPick(slot) },
                shape = RoundedCornerShape(20.dp),
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.62f),
                border = BorderStroke(1.dp, Color.White.copy(alpha = 0.48f)),
            ) {
                Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(font?.name ?: "选择字体", modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Icon(Icons.Rounded.KeyboardArrowDown, contentDescription = null)
                }
            }
            if (font != null) {
                Spacer(Modifier.height(12.dp))
                NativeFontPreview(
                    font = font,
                    text = when (slot) {
                        MixSlot.Cjk -> "洛书中文  Aa  0123"
                        MixSlot.Latin -> "LuoShu Typography 0123"
                        MixSlot.Digit -> "0123456789 Aa"
                    },
                    axes = axes,
                    modifier = Modifier.fillMaxWidth().height(66.dp).padding(horizontal = 4.dp),
                    textSizeSp = 25f,
                    gravity = Gravity.CENTER,
                    maxLines = 1,
                )
                Spacer(Modifier.height(12.dp))
                Alpha15WeightControl(
                    font = font,
                    value = weight,
                    axes = axes,
                    enabled = !state.busy,
                    onValue = { viewModel.updateMixWeight(slot, it) },
                    onAxis = { tag, axisValue -> viewModel.updateMixAxis(slot, tag, axisValue) },
                )
                Spacer(Modifier.height(14.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.07f))
                Spacer(Modifier.height(13.dp))
                Alpha15CoveragePanel(features, font, slot)
            }
        }
    }
}

@Composable
private fun Alpha15WeightControl(
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
                Text("正在读取字体内部 fvar 轴…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
        }
        font.variable && axisInfo.axes.isNotEmpty() -> {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("字体设计轴 · 真实实时预览", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        Text("这里控制字体实例，不等同于上页的系统全局粗细", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                    Alpha15Pill("${axisInfo.axes.size} 个轴", Color(0xFF8061DC))
                }
                axisInfo.axes.forEach { axis ->
                    val minimum = axis.min.coerceAtMost(axis.max)
                    val maximum = axis.max.coerceAtLeast(axis.min)
                    val current = (axes[axis.tag] ?: axis.default).coerceIn(minimum, maximum)
                    val isWeight = axis.tag == "wght"
                    val steps = if (isWeight && maximum > minimum) {
                        (((maximum - minimum) / 10f).roundToInt() - 1).coerceAtLeast(0)
                    } else {
                        0
                    }
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("${axis.tag} · ${axisName15(axis.tag)}", fontWeight = FontWeight.Bold, fontSize = 11.sp)
                            Spacer(Modifier.weight(1f))
                            Text(axisLabel15(current), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                        Slider(
                            value = current,
                            onValueChange = { raw ->
                                val next = if (isWeight) {
                                    ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum)
                                } else {
                                    raw.coerceIn(minimum, maximum)
                                }
                                onAxis(axis.tag, next)
                            },
                            enabled = enabled,
                            valueRange = minimum..maximum,
                            steps = steps,
                        )
                        if (isWeight) {
                            Text(
                                "字体原始默认 ${axisLabel15(axis.default)} · 系统 Regular 400 · 当前 ${axisLabel15(current)}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 9.sp,
                            )
                            Spacer(Modifier.height(7.dp))
                            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Alpha15ChoiceChip(
                                    text = "原始 ${axisLabel15(axis.default)}",
                                    selected = abs(current - axis.default) < 0.5f,
                                    enabled = enabled,
                                    onClick = { onAxis(axis.tag, axis.default) },
                                )
                                if (400f in minimum..maximum) {
                                    Alpha15ChoiceChip(
                                        text = "Regular 400",
                                        selected = abs(current - 400f) < 0.5f,
                                        enabled = enabled,
                                        onClick = { onAxis(axis.tag, 400f) },
                                    )
                                }
                            }
                        } else {
                            Text(
                                "${axisLabel15(minimum)} · 原始默认 ${axisLabel15(axis.default)} · ${axisLabel15(maximum)}",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 9.sp,
                            )
                        }
                    }
                }
                Text("拖动只更新 App 内预览；最终参数在点击应用后才写入模块。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
            }
        }
        font.variable -> {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("可变轴读取失败", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text(axisInfo.error.ifBlank { "字体没有可用的 fvar 轴。" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                Alpha15Pill("固定预览", Color(0xFF8061DC))
            }
        }
        staticWeights15(font).size >= 2 -> {
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("真实静态多字重", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        Text("每个档位会重新加载对应的真实字体文件", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                    Text(value.toString(), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                }
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    staticWeights15(font).forEach { option ->
                        Alpha15ChoiceChip(
                            text = weightName15(option),
                            selected = option == value,
                            enabled = enabled,
                            onClick = { onValue(option) },
                        )
                    }
                }
            }
        }
        else -> {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("固定字重", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("该字体没有可调轴，也没有其他静态字重文件。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                Alpha15Pill(weightName15(fixedWeight15(font)), Color(0xFF8061DC))
            }
        }
    }
}

@Composable
private fun Alpha15CoveragePanel(features: Alpha15FeatureViewModel, font: FontItem, slot: MixSlot) {
    val probe = features.coverage
    val isCurrent = probe.fontId == font.id
    val metrics = probe.metrics.takeIf { isCurrent }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("字形覆盖诊断", fontWeight = FontWeight.Bold, fontSize = 12.sp)
            Text("判断缺字 fallback 风险，不判断应用是否内置字体", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        }
        when {
            probe.loading && isCurrent -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            else -> OutlinedButton(
                onClick = { features.inspectCoverage(font.id) },
                shape = RoundedCornerShape(14.dp),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 5.dp),
            ) { Text(if (metrics == null) "检测" else "重测", fontSize = 11.sp) }
        }
    }
    if (isCurrent && probe.error.isNotBlank()) {
        Spacer(Modifier.height(8.dp))
        Text(probe.error, color = MaterialTheme.colorScheme.error, fontSize = 10.sp)
    }
    if (metrics != null) {
        Spacer(Modifier.height(12.dp))
        Alpha15CoverageRow("中文", metrics.cjkRatio, "${metrics.cjkPresent}/${metrics.cjkTotal}")
        Alpha15CoverageRow("英文", metrics.latinRatio, "${metrics.latinPresent}/${metrics.latinTotal}")
        Alpha15CoverageRow("数字", metrics.digitRatio, "${metrics.digitPresent}/${metrics.digitTotal}")
        Alpha15CoverageRow("标点", metrics.punctuationRatio, "${metrics.punctuationPresent}/${metrics.punctuationTotal}")
        Spacer(Modifier.height(8.dp))
        val relevant = when (slot) {
            MixSlot.Cjk -> metrics.cjkRatio
            MixSlot.Latin -> metrics.latinRatio
            MixSlot.Digit -> minOf(metrics.digitRatio, metrics.punctuationRatio)
        }
        val riskText = when {
            relevant >= 0.98f -> "当前槽位覆盖完整，缺字 fallback 风险低"
            relevant >= 0.75f -> "当前槽位存在少量缺字，个别字符可能回退系统字体"
            else -> "当前槽位覆盖不足，容易出现应用内字体不一致"
        }
        Text(riskText, color = if (relevant >= 0.98f) Color(0xFF2F8B66) else MaterialTheme.colorScheme.error, fontSize = 10.sp)
        if (metrics.missingSample.isNotBlank()) {
            Text("常用中文缺失示例：${metrics.missingSample}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, maxLines = 2)
        }
    }
}

@Composable
private fun Alpha15CoverageRow(label: String, ratio: Float, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.width(38.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        LinearProgressIndicator(progress = { ratio }, modifier = Modifier.weight(1f).height(6.dp).clip(RoundedCornerShape(99.dp)))
        Spacer(Modifier.width(9.dp))
        Text(value, modifier = Modifier.width(82.dp), textAlign = TextAlign.End, fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    Spacer(Modifier.height(7.dp))
}

@Composable
private fun Alpha15FontPicker(
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("选择${if (slot == MixSlot.Cjk) "中文" else if (slot == MixSlot.Latin) "英文" else "数字"}字体", fontWeight = FontWeight.Black) },
        text = {
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 470.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(fonts, key = { it.id }) { font ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(19.dp)).clickable { onChoose(font) },
                        shape = RoundedCornerShape(19.dp),
                        color = if (font.id == selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.54f),
                    ) {
                        Row(Modifier.fillMaxWidth().padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(font.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(capabilityLabel15(font), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                            }
                            if (font.id == selected) Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
}

@Composable
private fun Alpha15LogsPage(logs: String, onRefresh: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxSize()) {
        Alpha15Header("DIAGNOSTICS", "运行日志", "字体任务、覆盖诊断与错误记录", onRefresh)
        Alpha15Glass(Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 6.dp), RoundedCornerShape(30.dp)) {
            SelectionContainer {
                Text(
                    logs,
                    modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(18.dp),
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
private fun Alpha15Glass(
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = RoundedCornerShape(28.dp),
    shadow: androidx.compose.ui.unit.Dp = 10.dp,
    content: @Composable () -> Unit,
) {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    Surface(
        modifier = modifier,
        shape = shape,
        color = if (dark) Color(0xFF252733).copy(alpha = 0.84f) else Color.White.copy(alpha = 0.80f),
        border = BorderStroke(1.dp, if (dark) Color.White.copy(alpha = 0.09f) else Color.White.copy(alpha = 0.77f)),
        shadowElevation = shadow,
        content = content,
    )
}

@Composable
private fun Alpha15MiniStatus(modifier: Modifier, icon: ImageVector, label: String, value: String) {
    Alpha15Glass(modifier, RoundedCornerShape(28.dp)) {
        Column(Modifier.padding(17.dp)) {
            Surface(Modifier.size(40.dp), RoundedCornerShape(14.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)) {
                Box(contentAlignment = Alignment.Center) { Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(21.dp)) }
            }
            Spacer(Modifier.height(13.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
            Text(value, fontWeight = FontWeight.Black, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun Alpha15ActionCard(modifier: Modifier, title: String, subtitle: String, icon: ImageVector, onClick: () -> Unit) {
    Surface(
        modifier = modifier.clip(RoundedCornerShape(28.dp)).clickable(onClick = onClick),
        shape = RoundedCornerShape(28.dp),
        color = Color.Transparent,
        shadowElevation = 10.dp,
    ) {
        Column(Modifier.background(Brush.linearGradient(listOf(Color(0xFF5578F2), Color(0xFF7A61E4)))).padding(17.dp)) {
            Icon(icon, contentDescription = null, tint = Color.White)
            Spacer(Modifier.height(18.dp))
            Text(title, color = Color.White, fontWeight = FontWeight.Black, fontSize = 16.sp)
            Text(subtitle, color = Color.White.copy(alpha = 0.73f), fontSize = 10.sp, maxLines = 1)
        }
    }
}

@Composable
private fun Alpha15Pill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = 0.12f)) {
        Text(text, modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = color, fontSize = 10.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun Alpha15ChoiceChip(text: String, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clip(RoundedCornerShape(999.dp)).clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface.copy(alpha = 0.68f),
        border = BorderStroke(1.dp, if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.10f)),
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp),
            color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun Alpha15Operation(viewModel: LuoShuViewModel, modifier: Modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
    Alpha15Glass(modifier, RoundedCornerShape(24.dp)) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            if (viewModel.operationBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            else Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(10.dp))
            Text(viewModel.operationMessage, modifier = Modifier.weight(1f), fontSize = 12.sp)
        }
    }
}

@Composable
private fun Alpha15Error(message: String, modifier: Modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(25.dp),
        color = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.84f),
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
            Spacer(Modifier.width(10.dp))
            Text(message, modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer, fontSize = 12.sp)
        }
    }
}

private fun selectedFontId15(state: MixState, slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> state.cjk
    MixSlot.Latin -> state.latin
    MixSlot.Digit -> state.digit
}

private fun selectedWeight15(state: MixState, slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> state.cjkWeight
    MixSlot.Latin -> state.latinWeight
    MixSlot.Digit -> state.digitWeight
}

private fun selectedAxes15(state: MixState, slot: MixSlot): Map<String, Float> = when (slot) {
    MixSlot.Cjk -> state.cjkAxes
    MixSlot.Latin -> state.latinAxes
    MixSlot.Digit -> state.digitAxes
}

private fun staticWeights15(font: FontItem): List<Int> = font.weights
    .filterNot { it == "variable" }
    .map(::roleWeight15)
    .distinct()
    .sorted()

private fun fixedWeight15(font: FontItem): Int = staticWeights15(font).firstOrNull() ?: 400

private fun normalizedWeight15(font: FontItem, current: Int): Int = when {
    font.variable -> current.coerceIn(100, 900)
    staticWeights15(font).size >= 2 -> staticWeights15(font).minByOrNull { abs(it - current) } ?: 400
    else -> fixedWeight15(font)
}

private fun capabilityLabel15(font: FontItem): String = when {
    font.variable -> "可变字体"
    staticWeights15(font).size >= 2 -> "${staticWeights15(font).size} 档静态字重"
    else -> "固定 ${weightName15(fixedWeight15(font))}"
}

private fun roleWeight15(role: String): Int = when (role.lowercase()) {
    "thin" -> 100
    "extralight" -> 200
    "light" -> 300
    "regular", "normal" -> 400
    "medium" -> 500
    "semibold" -> 600
    "bold" -> 700
    "extrabold" -> 800
    "black", "heavy" -> 900
    else -> 400
}

private fun weightName15(weight: Int): String = when (weight) {
    100 -> "Thin 100"
    200 -> "ExtraLight 200"
    300 -> "Light 300"
    400 -> "Regular 400"
    500 -> "Medium 500"
    600 -> "SemiBold 600"
    700 -> "Bold 700"
    800 -> "ExtraBold 800"
    900 -> "Black 900"
    else -> weight.toString()
}

private fun axisName15(tag: String): String = when (tag) {
    "wght" -> "字重"
    "wdth" -> "宽度"
    "opsz" -> "光学尺寸"
    "slnt" -> "倾斜"
    "ital" -> "斜体开关"
    else -> "自定义轴"
}

private fun axisLabel15(value: Float): String = if (value % 1f == 0f) {
    value.roundToInt().toString()
} else {
    value.toString().trimEnd('0').trimEnd('.')
}

private fun directApplyCandidate15(state: MixState, fonts: List<FontItem>): FontItem? {
    val id = state.cjk.takeIf { it.isNotBlank() && it == state.latin && it == state.digit } ?: return null
    val font = fonts.firstOrNull { it.id == id && it.valid } ?: return null
    val maps = listOf(state.cjkAxes, state.latinAxes, state.digitAxes)
    if (!maps.all { axesEquivalent15(it, maps.first()) }) return null
    val normalized = maps.first().filterValues { it.isFinite() }
    if (normalized.keys.any { it != "wght" }) return null
    val weight = normalized["wght"] ?: 400f
    if (abs(weight - 400f) > 0.5f) return null
    return font
}

private fun axesEquivalent15(first: Map<String, Float>, second: Map<String, Float>): Boolean {
    val keys = first.keys + second.keys
    return keys.all { key -> abs((first[key] ?: defaultAxisValue15(key)) - (second[key] ?: defaultAxisValue15(key))) < 0.01f }
}

private fun defaultAxisValue15(tag: String): Float = if (tag == "wght") 400f else 0f

private fun alpha15Accent(seed: String): Color {
    val palette = listOf(
        Color(0xFF4278F2),
        Color(0xFF765BDE),
        Color(0xFF2F8B74),
        Color(0xFFD06486),
        Color(0xFFC17A32),
    )
    return palette[(seed.hashCode() and Int.MAX_VALUE) % palette.size]
}
