package io.github.xgl34222220.luoshu

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Extension
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.List
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.TextFields
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlin.math.roundToInt

private enum class AppPage(val title: String, val subtitle: String, val icon: ImageVector) {
    Overview("概览", "模块状态与快捷操作", Icons.Rounded.Home),
    Library("字体库", "搜索、应用与管理", Icons.Rounded.List),
    Mix("组合", "中文、英文与数字独立组合", Icons.Rounded.Build),
    Logs("日志", "后台任务与诊断记录", Icons.Rounded.Description),
}

private val LuoShuLight = lightColorScheme(
    primary = Color(0xFF3568E8),
    onPrimary = Color.White,
    secondary = Color(0xFF7158CE),
    background = Color(0xFFF6F7FB),
    surface = Color.White,
    surfaceVariant = Color(0xFFF0F2F8),
    onSurface = Color(0xFF181B24),
    onSurfaceVariant = Color(0xFF666B7A),
)

private val LuoShuDark = darkColorScheme(
    primary = Color(0xFFA9BEFF),
    onPrimary = Color(0xFF08265F),
    secondary = Color(0xFFD0BCFF),
    background = Color(0xFF0F1117),
    surface = Color(0xFF171A22),
    surfaceVariant = Color(0xFF232733),
    onSurface = Color(0xFFF1F2F6),
    onSurfaceVariant = Color(0xFFB4B8C5),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun LuoShuApp(viewModel: LuoShuViewModel = viewModel()) {
    var page by rememberSaveable { mutableStateOf(AppPage.Overview) }
    var pendingApply by remember { mutableStateOf<FontItem?>(null) }
    var pendingDelete by remember { mutableStateOf<FontItem?>(null) }
    var restoreDefault by remember { mutableStateOf(false) }
    var pickerSlot by remember { mutableStateOf<MixSlot?>(null) }

    LaunchedEffect(Unit) { viewModel.refresh() }
    LaunchedEffect(page) {
        when (page) {
            AppPage.Library -> viewModel.ensureFonts()
            AppPage.Mix -> {
                viewModel.ensureFonts()
                viewModel.refreshMixConfig()
            }
            AppPage.Logs -> viewModel.refreshLogs()
            AppPage.Overview -> Unit
        }
    }
    BackHandler(enabled = page != AppPage.Overview) { page = AppPage.Overview }

    MaterialTheme(
        colorScheme = if (androidx.compose.foundation.isSystemInDarkTheme()) LuoShuDark else LuoShuLight,
    ) {
        Scaffold(
            containerColor = MaterialTheme.colorScheme.background,
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text(page.title, fontWeight = FontWeight.Black)
                            Text(page.subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                        }
                    },
                    actions = {
                        IconButton(
                            onClick = {
                                when (page) {
                                    AppPage.Overview -> viewModel.refresh()
                                    AppPage.Library -> viewModel.refreshFonts(force = true)
                                    AppPage.Mix -> {
                                        viewModel.refreshFonts(force = true)
                                        viewModel.refreshMixConfig()
                                    }
                                    AppPage.Logs -> viewModel.refreshLogs()
                                }
                            },
                        ) {
                            Icon(Icons.Rounded.Refresh, contentDescription = "刷新")
                        }
                    },
                )
            },
            bottomBar = {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp) {
                    AppPage.entries.forEach { target ->
                        NavigationBarItem(
                            selected = page == target,
                            onClick = { page = target },
                            icon = { Icon(target.icon, contentDescription = null) },
                            label = { Text(target.title) },
                        )
                    }
                }
            },
        ) { padding ->
            when (page) {
                AppPage.Overview -> OverviewPage(
                    viewModel = viewModel,
                    onOpenLibrary = { page = AppPage.Library },
                    onOpenMix = { page = AppPage.Mix },
                    onRestoreDefault = { restoreDefault = true },
                    modifier = Modifier.padding(padding),
                )
                AppPage.Library -> LibraryPage(
                    viewModel = viewModel,
                    onApply = { pendingApply = it },
                    onDelete = { pendingDelete = it },
                    onRestoreDefault = { restoreDefault = true },
                    modifier = Modifier.padding(padding),
                )
                AppPage.Mix -> MixPage(
                    viewModel = viewModel,
                    onPick = { pickerSlot = it },
                    modifier = Modifier.padding(padding),
                )
                AppPage.Logs -> LogsPage(
                    logs = viewModel.logs,
                    modifier = Modifier.padding(padding),
                )
            }
        }

        pendingApply?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingApply = null },
                title = { Text("应用字体") },
                text = { Text("确定切换到「${font.name}」吗？生成完成后需要完整重启手机。") },
                confirmButton = {
                    TextButton(onClick = {
                        pendingApply = null
                        viewModel.applyFont(font.id)
                    }) { Text("应用") }
                },
                dismissButton = { TextButton(onClick = { pendingApply = null }) { Text("取消") } },
            )
        }

        if (restoreDefault) {
            AlertDialog(
                onDismissRequest = { restoreDefault = false },
                title = { Text("恢复系统字体") },
                text = { Text("确定恢复系统默认字体吗？完成后需要完整重启手机。") },
                confirmButton = {
                    TextButton(onClick = {
                        restoreDefault = false
                        viewModel.applyFont("default")
                    }) { Text("恢复") }
                },
                dismissButton = { TextButton(onClick = { restoreDefault = false }) { Text("取消") } },
            )
        }

        pendingDelete?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingDelete = null },
                title = { Text("删除字体") },
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

        pickerSlot?.let { slot ->
            FontPickerDialog(
                title = when (slot) {
                    MixSlot.Cjk -> "选择中文基底"
                    MixSlot.Latin -> "选择英文字体"
                    MixSlot.Digit -> "选择数字字体"
                },
                fonts = viewModel.fonts.filter { it.valid },
                selectedId = when (slot) {
                    MixSlot.Cjk -> viewModel.mixState.cjk
                    MixSlot.Latin -> viewModel.mixState.latin
                    MixSlot.Digit -> viewModel.mixState.digit
                },
                onSelect = {
                    viewModel.updateMixFont(slot, it.id)
                    pickerSlot = null
                },
                onDismiss = { pickerSlot = null },
            )
        }
    }
}

@Composable
private fun OverviewPage(
    viewModel: LuoShuViewModel,
    onOpenLibrary: () -> Unit,
    onOpenMix: () -> Unit,
    onRestoreDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val snapshot = viewModel.snapshot
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Surface(shape = RoundedCornerShape(28.dp), color = Color.Transparent, shadowElevation = 4.dp) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(
                            Brush.linearGradient(
                                listOf(Color(0xFF2F6BE6), Color(0xFF5C62E6), Color(0xFF805BC7)),
                            ),
                        )
                        .padding(20.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            modifier = Modifier.size(50.dp),
                            shape = RoundedCornerShape(17.dp),
                            color = Color.White.copy(alpha = 0.18f),
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text("洛", color = Color.White, fontWeight = FontWeight.Black, fontSize = 22.sp)
                            }
                        }
                        Spacer(Modifier.width(13.dp))
                        Column(Modifier.weight(1f)) {
                            Text(snapshot.version, color = Color.White, fontWeight = FontWeight.Black, fontSize = 20.sp)
                            Text(
                                if (snapshot.installed) "模块与原生 App 已连接" else "等待连接洛书模块",
                                color = Color.White.copy(alpha = 0.78f),
                                fontSize = 11.sp,
                            )
                        }
                        if (snapshot.loading) CircularProgressIndicator(
                            modifier = Modifier.size(22.dp),
                            color = Color.White,
                            strokeWidth = 2.5.dp,
                        ) else Icon(
                            if (snapshot.installed) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                            contentDescription = null,
                            tint = Color.White,
                        )
                    }
                    Spacer(Modifier.height(18.dp))
                    Text(snapshot.activeLabel, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text(
                        "${snapshot.rootManager} · ${snapshot.mountEngine}",
                        color = Color.White.copy(alpha = 0.75f),
                        fontSize = 11.sp,
                    )
                }
            }
        }

        if (snapshot.error.isNotBlank()) item { ErrorCard(snapshot.error) }
        if (viewModel.operationMessage.isNotBlank()) item { OperationCard(viewModel) }
        if (viewModel.mixState.busy || viewModel.mixState.taskState == "success" || viewModel.mixState.taskState == "failed") {
            item { MixProgressCard(viewModel.mixState) }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusCard(Modifier.weight(1f), Icons.Rounded.Security, "Root", if (snapshot.rootGranted) "已授权" else "未授权", snapshot.rootManager)
                StatusCard(Modifier.weight(1f), Icons.Rounded.Extension, "模块", if (snapshot.installed) "已连接" else "未连接", "Code ${snapshot.versionCode}")
            }
        }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusCard(Modifier.weight(1f), Icons.Rounded.TextFields, "当前字体", snapshot.activeLabel, snapshot.activeFont)
                StatusCard(Modifier.weight(1f), Icons.Rounded.Build, "后台任务", snapshot.taskState, snapshot.taskMessage)
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onOpenLibrary,
                    enabled = snapshot.rootGranted && snapshot.installed,
                    modifier = Modifier.weight(1f).height(54.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Icon(Icons.Rounded.List, contentDescription = null)
                    Spacer(Modifier.width(7.dp))
                    Text("字体库", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = onOpenMix,
                    enabled = snapshot.rootGranted && snapshot.installed,
                    modifier = Modifier.weight(1f).height(54.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Icon(Icons.Rounded.Build, contentDescription = null)
                    Spacer(Modifier.width(7.dp))
                    Text("字体组合", fontWeight = FontWeight.Bold)
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onRestoreDefault,
                    enabled = !viewModel.operationBusy && !viewModel.mixState.busy,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(16.dp),
                ) { Text("恢复系统字体") }
                Button(
                    onClick = viewModel::rebootDevice,
                    enabled = viewModel.rebootRequired && !viewModel.operationBusy && !viewModel.mixState.busy,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(16.dp),
                ) { Text("立即重启") }
            }
        }
    }
}

@Composable
private fun LibraryPage(
    viewModel: LuoShuViewModel,
    onApply: (FontItem) -> Unit,
    onDelete: (FontItem) -> Unit,
    onRestoreDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier = modifier.fillMaxSize()) {
        if (viewModel.fontLoading || viewModel.operationBusy) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        OutlinedTextField(
            value = viewModel.searchQuery,
            onValueChange = viewModel::setSearchQuery,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
            leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
            placeholder = { Text("搜索字体名称或格式") },
        )

        if (viewModel.fontError.isNotBlank()) ErrorCard(viewModel.fontError, Modifier.padding(horizontal = 16.dp))
        if (viewModel.operationMessage.isNotBlank()) OperationCard(viewModel, Modifier.padding(horizontal = 16.dp, vertical = 6.dp))

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                SystemFontCard(
                    active = viewModel.snapshot.activeFont == "default",
                    busy = viewModel.operationBusy || viewModel.mixState.busy,
                    onRestoreDefault = onRestoreDefault,
                )
            }
            if (!viewModel.fontLoading && viewModel.filteredFonts.isEmpty()) {
                item { EmptyFontCard(viewModel.searchQuery) }
            }
            items(viewModel.filteredFonts, key = { it.id }) { font ->
                FontCard(
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
private fun MixPage(
    viewModel: LuoShuViewModel,
    onPick: (MixSlot) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state = viewModel.mixState
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (viewModel.fontLoading || state.loading) {
            item { LinearProgressIndicator(modifier = Modifier.fillMaxWidth()) }
        }
        if (viewModel.fontError.isNotBlank()) item { ErrorCard(viewModel.fontError) }
        if (state.error.isNotBlank()) item { ErrorCard(state.error) }

        item {
            Card(
                shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.08f)),
            ) {
                Column(Modifier.fillMaxWidth().padding(18.dp)) {
                    Text("原生复合字体", fontWeight = FontWeight.Black, fontSize = 18.sp)
                    Spacer(Modifier.height(5.dp))
                    Text(
                        "中文作为完整基底，英文与数字只替换对应字形。选择完成后直接提交模块后台生成，不再加载 WebUI。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        lineHeight = 18.sp,
                    )
                }
            }
        }

        item {
            MixSlotCard(
                mark = "中",
                title = "中文基底",
                font = viewModel.fonts.firstOrNull { it.id == state.cjk },
                weight = state.cjkWeight,
                enabled = !state.busy && !viewModel.fontLoading,
                onPick = { onPick(MixSlot.Cjk) },
                onWeight = { viewModel.updateMixWeight(MixSlot.Cjk, it) },
            )
        }
        item {
            MixSlotCard(
                mark = "Aa",
                title = "英文字形",
                font = viewModel.fonts.firstOrNull { it.id == state.latin },
                weight = state.latinWeight,
                enabled = !state.busy && !viewModel.fontLoading,
                onPick = { onPick(MixSlot.Latin) },
                onWeight = { viewModel.updateMixWeight(MixSlot.Latin, it) },
            )
        }
        item {
            MixSlotCard(
                mark = "123",
                title = "数字字形",
                font = viewModel.fonts.firstOrNull { it.id == state.digit },
                weight = state.digitWeight,
                enabled = !state.busy && !viewModel.fontLoading,
                onPick = { onPick(MixSlot.Digit) },
                onWeight = { viewModel.updateMixWeight(MixSlot.Digit, it) },
            )
        }

        if (state.busy || state.taskState == "success" || state.taskState == "failed") {
            item { MixProgressCard(state) }
        }

        item {
            Button(
                onClick = viewModel::startMix,
                enabled = !state.busy && !viewModel.operationBusy && viewModel.fonts.isNotEmpty() &&
                    state.cjk.isNotBlank() && state.latin.isNotBlank() && state.digit.isNotBlank(),
                modifier = Modifier.fillMaxWidth().height(56.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                if (state.busy) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                    Spacer(Modifier.width(9.dp))
                    Text("后台生成中")
                } else {
                    Text("生成并应用复合字体", fontWeight = FontWeight.Bold)
                }
            }
        }

        item {
            Text(
                "当前核心版只提供稳定的字重参数。字宽、光学尺寸、倾斜等高级可变轴将在原生解析完成后再加入，不再使用会卡住的 WebView 工作台。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                lineHeight = 17.sp,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}

@Composable
private fun MixSlotCard(
    mark: String,
    title: String,
    font: FontItem?,
    weight: Int,
    enabled: Boolean,
    onPick: () -> Unit,
    onWeight: (Int) -> Unit,
) {
    Card(shape = RoundedCornerShape(24.dp)) {
        Column(Modifier.fillMaxWidth().padding(17.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(mark, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Text(
                        font?.let { "${it.name} · ${it.format}" } ?: "请选择字体",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                OutlinedButton(onClick = onPick, enabled = enabled, shape = RoundedCornerShape(14.dp)) {
                    Text("选择")
                    Icon(Icons.Rounded.KeyboardArrowDown, contentDescription = null, modifier = Modifier.size(18.dp))
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("目标字重", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                Spacer(Modifier.weight(1f))
                Text(weight.toString(), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black, fontSize = 16.sp)
            }
            Slider(
                value = weight.toFloat(),
                onValueChange = { onWeight((it / 10f).roundToInt() * 10) },
                valueRange = 100f..900f,
                enabled = enabled,
            )
            Row(Modifier.fillMaxWidth()) {
                Text("100", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
                Spacer(Modifier.weight(1f))
                Text("400 常规", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
                Spacer(Modifier.weight(1f))
                Text("900", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
            }
            if (font != null) {
                Spacer(Modifier.height(7.dp))
                Text(
                    if (font.variable) "可变字体：该字重会直接实例化到最终字体" else "静态字体：模块会选择最接近目标字重的真实文件",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                )
            }
        }
    }
}

@Composable
private fun FontPickerDialog(
    title: String,
    fonts: List<FontItem>,
    selectedId: String,
    onSelect: (FontItem) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            if (fonts.isEmpty()) {
                Text("字体库为空，请先把字体放入 /sdcard/LuoShu/fonts/ 并刷新。")
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 430.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    items(fonts, key = { it.id }) { font ->
                        Surface(
                            modifier = Modifier.fillMaxWidth().clickable { onSelect(font) },
                            shape = RoundedCornerShape(15.dp),
                            color = if (font.id == selectedId) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else MaterialTheme.colorScheme.surfaceVariant,
                        ) {
                            Row(Modifier.fillMaxWidth().padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(font.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text("${font.format} · ${font.weightLabel}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                                }
                                if (font.id == selectedId) Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
    )
}

@Composable
private fun MixProgressCard(state: MixState) {
    Card(
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(
            containerColor = when (state.taskState) {
                "failed" -> MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.primary.copy(alpha = 0.08f)
            },
        ),
    ) {
        Column(Modifier.fillMaxWidth().padding(15.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (state.busy) CircularProgressIndicator(modifier = Modifier.size(21.dp), strokeWidth = 2.dp)
                else Icon(
                    if (state.taskState == "failed") Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    tint = if (state.taskState == "failed") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        when (state.taskState) {
                            "success" -> "复合字体已完成"
                            "failed" -> "复合字体生成失败"
                            else -> "后台生成中"
                        },
                        fontWeight = FontWeight.Bold,
                    )
                    Text(state.message, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
                Text("${state.progress}%", fontWeight = FontWeight.Black, color = MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.height(10.dp))
            LinearProgressIndicator(
                progress = { state.progress.coerceIn(0, 100) / 100f },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun SystemFontCard(active: Boolean, busy: Boolean, onRestoreDefault: () -> Unit) {
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (active) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f) else MaterialTheme.colorScheme.surface,
        ),
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
                Text("系", modifier = Modifier.padding(horizontal = 15.dp, vertical = 13.dp), fontWeight = FontWeight.Black)
            }
            Spacer(Modifier.width(13.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text("恢复 ROM 自带字体配置", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
            if (active) Text("使用中", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, fontSize = 12.sp)
            else Button(onClick = onRestoreDefault, enabled = !busy, shape = RoundedCornerShape(14.dp)) { Text("恢复") }
        }
    }
}

@Composable
private fun FontCard(font: FontItem, active: Boolean, busy: Boolean, onApply: () -> Unit, onDelete: () -> Unit) {
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (active) MaterialTheme.colorScheme.primary.copy(alpha = 0.10f) else MaterialTheme.colorScheme.surface,
        ),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(50.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = if (font.valid) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else MaterialTheme.colorScheme.errorContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = if (font.valid) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(font.name, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        "${font.format}${font.size.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""}${font.date.takeIf { it.isNotBlank() }?.let { " · $it" } ?: ""}",
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
            Spacer(Modifier.height(12.dp))
            Text("洛书字体预览 · Hello 0123456789", fontSize = 20.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(7.dp))
            Text(
                if (font.valid) font.weightLabel else font.error.ifBlank { "字体文件无效" },
                color = if (font.valid) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.error,
                fontSize = 11.sp,
            )
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (font.variable) {
                    Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.secondary.copy(alpha = 0.12f)) {
                        Text("可变", modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp), color = MaterialTheme.colorScheme.secondary, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    }
                }
                Spacer(Modifier.weight(1f))
                if (active) {
                    Text("当前使用", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                } else {
                    Button(onClick = onApply, enabled = font.valid && !busy, shape = RoundedCornerShape(14.dp)) {
                        Text("应用字体")
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyFontCard(query: String) {
    Card(shape = RoundedCornerShape(22.dp)) {
        Column(Modifier.fillMaxWidth().padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("没有找到字体", fontWeight = FontWeight.Bold)
            Text(
                if (query.isBlank()) "请先把字体放入 /sdcard/LuoShu/fonts/" else "换一个关键词试试",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun OperationCard(viewModel: LuoShuViewModel, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.08f)),
    ) {
        Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            if (viewModel.operationBusy) CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
            else Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(10.dp))
            Text(viewModel.operationMessage, modifier = Modifier.weight(1f), fontSize = 12.sp, lineHeight = 17.sp)
        }
    }
}

@Composable
private fun ErrorCard(message: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
        shape = RoundedCornerShape(20.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(16.dp)) {
            Text("连接异常", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onErrorContainer)
            Text(message, fontSize = 12.sp, color = MaterialTheme.colorScheme.onErrorContainer)
        }
    }
}

@Composable
private fun StatusCard(modifier: Modifier, icon: ImageVector, label: String, value: String, detail: String) {
    Card(modifier = modifier, shape = RoundedCornerShape(22.dp)) {
        Column(Modifier.padding(15.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(22.dp))
            Spacer(Modifier.height(12.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
            Text(value, fontWeight = FontWeight.Bold, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(detail, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun LogsPage(logs: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxSize().padding(16.dp),
        shape = RoundedCornerShape(24.dp),
        color = MaterialTheme.colorScheme.surface,
    ) {
        SelectionContainer {
            Text(
                logs,
                modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
                fontFamily = FontFamily.Monospace,
                fontSize = 10.sp,
                lineHeight = 15.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
