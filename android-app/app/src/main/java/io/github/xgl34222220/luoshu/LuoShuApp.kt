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
import androidx.compose.material.icons.rounded.TextFields
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlin.math.abs
import kotlin.math.roundToInt

private enum class AppPage(val title: String, val subtitle: String, val icon: ImageVector) {
    Overview("概览", "模块与任务", Icons.Rounded.Home),
    Library("字体库", "浏览与应用", Icons.Rounded.List),
    Mix("组合", "中文 · 英文 · 数字", Icons.Rounded.Layers),
    Logs("日志", "运行诊断", Icons.Rounded.Description),
}

private val LuoShuLight = lightColorScheme(
    primary = Color(0xFF3975F4),
    onPrimary = Color.White,
    secondary = Color(0xFF7658E8),
    background = Color(0xFFF4F5FB),
    surface = Color.White,
    surfaceVariant = Color(0xFFF0F1F8),
    onSurface = Color(0xFF151722),
    onSurfaceVariant = Color(0xFF6D7080),
)

private val LuoShuDark = darkColorScheme(
    primary = Color(0xFFAEC5FF),
    onPrimary = Color(0xFF0A2D69),
    secondary = Color(0xFFD0C1FF),
    background = Color(0xFF101117),
    surface = Color(0xFF191B24),
    surfaceVariant = Color(0xFF252833),
    onSurface = Color(0xFFF4F4F8),
    onSurfaceVariant = Color(0xFFB6B8C4),
)

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
        Box(Modifier.fillMaxSize()) {
            MiuiXBackdrop()
            Scaffold(
                modifier = Modifier.fillMaxSize(),
                containerColor = Color.Transparent,
                bottomBar = {
                    FloatingDock(
                        current = page,
                        onSelect = { page = it },
                    )
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
        }

        pendingApply?.let { font ->
            AlertDialog(
                onDismissRequest = { pendingApply = null },
                title = { Text("应用字体", fontWeight = FontWeight.Black) },
                text = { Text("确定切换到「${font.name}」吗？完成后需要完整重启手机。") },
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
                text = { Text("恢复 ROM 自带字体配置，完成后需要完整重启手机。") },
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
            FontPickerDialog(
                slot = slot,
                fonts = viewModel.fonts.filter { it.valid },
                selected = selectedFontId(viewModel.mixState, slot),
                onDismiss = { pickerSlot = null },
                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(slot, normalizedWeight(font, selectedWeight(viewModel.mixState, slot)))
                    pickerSlot = null
                },
            )
        }
    }
}

@Composable
private fun MiuiXBackdrop() {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    val base = if (dark) {
        Brush.verticalGradient(listOf(Color(0xFF101117), Color(0xFF171827), Color(0xFF101117)))
    } else {
        Brush.verticalGradient(listOf(Color(0xFFF8F7FF), Color(0xFFF0F5FF), Color(0xFFF8F8FC)))
    }
    Box(Modifier.fillMaxSize().background(base)) {
        Box(
            Modifier
                .offset(x = 210.dp, y = (-60).dp)
                .size(290.dp)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFF7E65FF).copy(alpha = if (dark) 0.26f else 0.24f), Color.Transparent),
                    ),
                    CircleShape,
                ),
        )
        Box(
            Modifier
                .offset(x = (-100).dp, y = 430.dp)
                .size(320.dp)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFF4DA6FF).copy(alpha = if (dark) 0.20f else 0.18f), Color.Transparent),
                    ),
                    CircleShape,
                ),
        )
        Box(
            Modifier
                .offset(x = 230.dp, y = 760.dp)
                .size(260.dp)
                .background(
                    Brush.radialGradient(
                        listOf(Color(0xFFFF91D0).copy(alpha = if (dark) 0.12f else 0.12f), Color.Transparent),
                    ),
                    CircleShape,
                ),
        )
    }
}

@Composable
private fun FloatingDock(current: AppPage, onSelect: (AppPage) -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .navigationBarsPadding()
            .padding(horizontal = 18.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        GlassSurface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(32.dp),
            shadow = 18.dp,
        ) {
            Row(
                Modifier.fillMaxWidth().padding(7.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                AppPage.entries.forEach { page ->
                    val selected = page == current
                    Row(
                        modifier = Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(24.dp))
                            .background(
                                if (selected) Brush.horizontalGradient(
                                    listOf(Color(0xFF5B6EFF).copy(alpha = 0.18f), Color(0xFF8A5DFF).copy(alpha = 0.15f)),
                                ) else Brush.linearGradient(listOf(Color.Transparent, Color.Transparent)),
                            )
                            .clickable { onSelect(page) }
                            .padding(vertical = 10.dp),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            page.icon,
                            contentDescription = page.title,
                            modifier = Modifier.size(21.dp),
                            tint = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (selected) {
                            Spacer(Modifier.width(7.dp))
                            Text(page.title, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PageHeader(
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
            GlassSurface(shape = RoundedCornerShape(18.dp), shadow = 6.dp) {
                IconButton(onClick = it) { Icon(Icons.Rounded.Refresh, contentDescription = "刷新") }
            }
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
        contentPadding = PaddingValues(bottom = 22.dp),
        verticalArrangement = Arrangement.spacedBy(13.dp),
    ) {
        item { PageHeader("LUOSHU NATIVE", "洛书", "MIUIx 原生字体控制中心", viewModel::refresh) }
        item {
            Surface(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                shape = RoundedCornerShape(36.dp),
                color = Color.Transparent,
                shadowElevation = 18.dp,
            ) {
                Column(
                    modifier = Modifier
                        .background(
                            Brush.linearGradient(
                                listOf(Color(0xFF5268FF), Color(0xFF7258EB), Color(0xFF8A58D7)),
                            ),
                        )
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
                                if (snapshot.installed) "模块已连接 · ${snapshot.mountEngine}" else "等待连接匹配模块",
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
                    Text("当前字体", color = Color.White.copy(alpha = 0.68f), fontSize = 10.sp)
                    Text(snapshot.activeLabel, color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Black)
                    Spacer(Modifier.height(5.dp))
                    Text(snapshot.taskMessage, color = Color.White.copy(alpha = 0.76f), fontSize = 11.sp, maxLines = 2)
                }
            }
        }
        if (snapshot.error.isNotBlank()) item { ErrorGlass(snapshot.error) }
        if (viewModel.operationMessage.isNotBlank()) item { OperationGlass(viewModel) }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.spacedBy(11.dp),
            ) {
                MiniGlassStatus(Modifier.weight(1f), Icons.Rounded.Security, "Root", if (snapshot.rootGranted) snapshot.rootManager else "未授权")
                MiniGlassStatus(Modifier.weight(1f), Icons.Rounded.Layers, "引擎", snapshot.mountEngine)
            }
        }
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.spacedBy(11.dp),
            ) {
                GradientAction(Modifier.weight(1f), "字体库", "浏览和应用", Icons.Rounded.List, onOpenLibrary)
                GradientAction(Modifier.weight(1f), "字体组合", "中文 · 英文 · 数字", Icons.Rounded.AutoAwesome, onOpenMix)
            }
        }
        item {
            GlassSurface(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(28.dp)) {
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
private fun LibraryPage(
    viewModel: LuoShuViewModel,
    onApply: (FontItem) -> Unit,
    onDelete: (FontItem) -> Unit,
    onRestoreDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxSize()) {
        PageHeader("FONT LIBRARY", "字体库", "真实字体预览 · 懒加载", { viewModel.refreshFonts(force = true) })
        GlassSurface(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(24.dp)) {
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
            if (viewModel.fontError.isNotBlank()) item { ErrorGlass(viewModel.fontError, Modifier.fillMaxWidth()) }
            if (viewModel.operationMessage.isNotBlank()) item { OperationGlass(viewModel, Modifier.fillMaxWidth()) }
            item { SystemFontCard(viewModel.snapshot.activeFont == "default", viewModel.operationBusy, onRestoreDefault) }
            if (!viewModel.fontLoading && viewModel.filteredFonts.isEmpty()) {
                item {
                    GlassSurface(Modifier.fillMaxWidth(), RoundedCornerShape(30.dp)) {
                        Column(Modifier.fillMaxWidth().padding(34.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("没有找到字体", fontSize = 19.sp, fontWeight = FontWeight.Black)
                            Text("请将字体放入 /sdcard/LuoShu/fonts/", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                        }
                    }
                }
            }
            items(viewModel.filteredFonts, key = { it.id }) { font ->
                MiuiFontCard(
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
private fun SystemFontCard(active: Boolean, busy: Boolean, onRestoreDefault: () -> Unit) {
    GlassSurface(Modifier.fillMaxWidth(), RoundedCornerShape(30.dp)) {
        Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(Modifier.size(54.dp), RoundedCornerShape(18.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
                Box(contentAlignment = Alignment.Center) { Text("系", fontSize = 20.sp, fontWeight = FontWeight.Black) }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", fontSize = 17.sp, fontWeight = FontWeight.Black)
                Text("恢复 ROM 原始字体配置", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
            if (active) CapabilityPill("使用中", Color(0xFF3F7DF5))
            else Button(onClick = onRestoreDefault, enabled = !busy, shape = RoundedCornerShape(15.dp)) { Text("恢复") }
        }
    }
}

@Composable
private fun MiuiFontCard(font: FontItem, active: Boolean, busy: Boolean, onApply: () -> Unit, onDelete: () -> Unit) {
    GlassSurface(Modifier.fillMaxWidth(), RoundedCornerShape(32.dp), shadow = 12.dp) {
        Column(Modifier.fillMaxWidth().padding(17.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = accentFor(font.id).copy(alpha = 0.14f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = accentFor(font.id), fontSize = 17.sp, fontWeight = FontWeight.Black)
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
                CapabilityPill(capabilityLabel(font), accentFor(font.id))
                Spacer(Modifier.weight(1f))
                if (active) {
                    Text("当前使用", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black, fontSize = 12.sp)
                } else {
                    Button(
                        onClick = onApply,
                        enabled = font.valid && !busy,
                        shape = RoundedCornerShape(16.dp),
                    ) { Text("应用字体", fontWeight = FontWeight.Bold) }
                }
            }
        }
    }
}

@Composable
private fun MixPage(viewModel: LuoShuViewModel, onPick: (MixSlot) -> Unit, modifier: Modifier = Modifier) {
    val state = viewModel.mixState
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 22.dp),
        verticalArrangement = Arrangement.spacedBy(13.dp),
    ) {
        item { PageHeader("FONT MIX", "字体组合", "只有真实支持的字重能力才会显示", viewModel::refreshMixConfig) }
        if (viewModel.fontLoading || state.loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        if (state.error.isNotBlank()) item { ErrorGlass(state.error) }
        if (state.busy || state.taskState == "success") item {
            GlassSurface(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(28.dp)) {
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
        item { MixSlotCard(viewModel, MixSlot.Cjk, "中文基底", "完整保留中文与符号", onPick) }
        item { MixSlotCard(viewModel, MixSlot.Latin, "英文字形", "替换拉丁字母轮廓", onPick) }
        item { MixSlotCard(viewModel, MixSlot.Digit, "数字字形", "替换数字与相关标点", onPick) }
        item {
            GlassSurface(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(30.dp)) {
                Column(Modifier.fillMaxWidth().padding(18.dp)) {
                    Text("生成说明", fontWeight = FontWeight.Black)
                    Text(
                        "下方预览会随每个真实可变轴或静态字重档位即时变化；只有点击生成并应用后才会写入系统字体。已打开的应用仍需重新启动进程，系统界面通常需要完整重启。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        lineHeight = 17.sp,
                    )
                    Spacer(Modifier.height(15.dp))
                    Button(
                        onClick = viewModel::startMix,
                        enabled = !state.busy && !viewModel.operationBusy && viewModel.fonts.isNotEmpty(),
                        modifier = Modifier.fillMaxWidth().height(56.dp),
                        shape = RoundedCornerShape(19.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF4679F5)),
                    ) {
                        Icon(Icons.Rounded.AutoAwesome, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("生成并应用到系统", fontWeight = FontWeight.Black)
                    }
                }
            }
        }
    }
}

@Composable
private fun MixSlotCard(viewModel: LuoShuViewModel, slot: MixSlot, title: String, subtitle: String, onPick: (MixSlot) -> Unit) {
    val state = viewModel.mixState
    val fontId = selectedFontId(state, slot)
    val font = viewModel.fonts.firstOrNull { it.id == fontId }
    val weight = selectedWeight(state, slot)
    val axes = selectedAxes(state, slot)
    GlassSurface(Modifier.fillMaxWidth().padding(horizontal = 18.dp), RoundedCornerShape(32.dp), shadow = 12.dp) {
        Column(Modifier.fillMaxWidth().padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(Modifier.size(46.dp), RoundedCornerShape(16.dp), color = accentFor(title).copy(alpha = 0.14f)) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(if (slot == MixSlot.Cjk) "中" else if (slot == MixSlot.Latin) "Aa" else "123", color = accentFor(title), fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, fontWeight = FontWeight.Black, fontSize = 17.sp)
                    Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                CapabilityPill(font?.let(::capabilityLabel) ?: "未选择", accentFor(title))
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
                text = if (slot == MixSlot.Cjk) "洛书中文  Aa  0123" else if (slot == MixSlot.Latin) "LuoShu Typography 0123" else "0123456789 Aa",
                axes = axes,
                    modifier = Modifier.fillMaxWidth().height(62.dp).padding(horizontal = 4.dp),
                    textSizeSp = 25f,
                    gravity = Gravity.CENTER,
                    maxLines = 1,
                )
                Spacer(Modifier.height(12.dp))
                        WeightControl(
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
private fun WeightControl(
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
  Column(verticalArrangement = Arrangement.spacedBy(13.dp)) {
      Row(verticalAlignment = Alignment.CenterVertically) {
          Column(Modifier.weight(1f)) {
              Text("真实可变轴 · 实时预览", fontWeight = FontWeight.Bold, fontSize = 12.sp)
              Text("与 WebUI 工作台使用同一组轴参数", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
          }
          CapabilityPill("${axisInfo.axes.size} 个轴", Color(0xFF8A6CE8))
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
                  Text("${axis.tag} · ${axisDisplayName(axis.tag)}", fontWeight = FontWeight.Bold, fontSize = 11.sp)
                  Spacer(Modifier.weight(1f))
                  Text(axisValueLabel(current), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
              }
              Slider(
                  value = current,
                  onValueChange = { raw ->
                      val next = if (isWeight) ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum) else raw.coerceIn(minimum, maximum)
                      onAxis(axis.tag, next)
                  },
                  enabled = enabled,
                  valueRange = minimum..maximum,
                  steps = stepCount,
              )
              Text(
                  "${axisValueLabel(minimum)} · 默认 ${axisValueLabel(axis.default)} · ${axisValueLabel(maximum)}",
                  color = MaterialTheme.colorScheme.onSurfaceVariant,
                  fontSize = 9.sp,
              )
          }
      }
      Text("拖动时只刷新上方真实字体预览，不会反复改写系统文件。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
  }
        }
        font.variable -> {
  Row(verticalAlignment = Alignment.CenterVertically) {
      Column(Modifier.weight(1f)) {
          Text("可变字体轴读取失败", fontWeight = FontWeight.Bold, fontSize = 12.sp)
          Text(
              axisInfo.error.ifBlank { "字体没有可用的 fvar 轴。" },
              color = MaterialTheme.colorScheme.onSurfaceVariant,
              fontSize = 10.sp,
          )
      }
      CapabilityPill("固定预览", Color(0xFF8A6CE8))
  }
        }
        staticWeights(font).size >= 2 -> {
  Column {
      Row(verticalAlignment = Alignment.CenterVertically) {
          Text("真实静态字重 · 实时预览", fontWeight = FontWeight.Bold, fontSize = 12.sp)
          Spacer(Modifier.weight(1f))
          Text(value.toString(), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
      }
      Spacer(Modifier.height(9.dp))
      Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
          staticWeights(font).forEach { option ->
              val selected = option == value
              Surface(
                  modifier = Modifier.clip(RoundedCornerShape(999.dp)).clickable(enabled = enabled) { onValue(option) },
                  shape = RoundedCornerShape(999.dp),
                  color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface.copy(alpha = 0.66f),
                  border = BorderStroke(1.dp, if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline.copy(alpha = 0.18f)),
              ) {
                  Text(
                      weightName(option),
                      modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp),
                      color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                      fontSize = 11.sp,
                      fontWeight = FontWeight.Bold,
                  )
              }
          }
      }
      Spacer(Modifier.height(8.dp))
      Text("切换档位会重新加载该字体族对应的真实文件，不再固定预览 Regular。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
  }
        }
        else -> {
  Row(verticalAlignment = Alignment.CenterVertically) {
      Column(Modifier.weight(1f)) {
          Text("固定字重", fontWeight = FontWeight.Bold, fontSize = 12.sp)
          Text("该字体没有可调轴，也没有其他静态字重文件。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
      }
      CapabilityPill(weightName(fixedWeight(font)), Color(0xFF8A6CE8))
  }
        }
    }
}
@Composable
private fun FontPickerDialog(
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
                                Text(capabilityLabel(font), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
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
private fun LogsPage(logs: String, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxSize()) {
        PageHeader("DIAGNOSTICS", "运行日志", "字体任务与错误记录")
        GlassSurface(Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 6.dp), RoundedCornerShape(30.dp)) {
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
private fun GlassSurface(
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = RoundedCornerShape(28.dp),
    shadow: androidx.compose.ui.unit.Dp = 10.dp,
    content: @Composable () -> Unit,
) {
    val dark = androidx.compose.foundation.isSystemInDarkTheme()
    Surface(
        modifier = modifier,
        shape = shape,
        color = if (dark) Color(0xFF252733).copy(alpha = 0.82f) else Color.White.copy(alpha = 0.78f),
        border = BorderStroke(1.dp, if (dark) Color.White.copy(alpha = 0.09f) else Color.White.copy(alpha = 0.76f)),
        shadowElevation = shadow,
        content = content,
    )
}

@Composable
private fun MiniGlassStatus(modifier: Modifier, icon: ImageVector, label: String, value: String) {
    GlassSurface(modifier, RoundedCornerShape(28.dp)) {
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
private fun GradientAction(modifier: Modifier, title: String, subtitle: String, icon: ImageVector, onClick: () -> Unit) {
    Surface(modifier = modifier.clip(RoundedCornerShape(28.dp)).clickable(onClick = onClick), shape = RoundedCornerShape(28.dp), color = Color.Transparent, shadowElevation = 10.dp) {
        Column(
            Modifier.background(Brush.linearGradient(listOf(Color(0xFF5A79F6), Color(0xFF7B63ED)))).padding(17.dp),
        ) {
            Icon(icon, contentDescription = null, tint = Color.White)
            Spacer(Modifier.height(18.dp))
            Text(title, color = Color.White, fontWeight = FontWeight.Black, fontSize = 16.sp)
            Text(subtitle, color = Color.White.copy(alpha = 0.72f), fontSize = 10.sp, maxLines = 1)
        }
    }
}

@Composable
private fun CapabilityPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = 0.12f)) {
        Text(text, modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = color, fontSize = 10.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun OperationGlass(viewModel: LuoShuViewModel, modifier: Modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
    GlassSurface(modifier, RoundedCornerShape(24.dp)) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            if (viewModel.operationBusy) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            else Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(10.dp))
            Text(viewModel.operationMessage, modifier = Modifier.weight(1f), fontSize = 12.sp)
        }
    }
}

@Composable
private fun ErrorGlass(message: String, modifier: Modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
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

private fun selectedFontId(state: MixState, slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> state.cjk
    MixSlot.Latin -> state.latin
    MixSlot.Digit -> state.digit
}

private fun selectedWeight(state: MixState, slot: MixSlot): Int = when (slot) {
        MixSlot.Cjk -> state.cjkWeight
        MixSlot.Latin -> state.latinWeight
        MixSlot.Digit -> state.digitWeight
    }

    private fun selectedAxes(state: MixState, slot: MixSlot): Map<String, Float> = when (slot) {
        MixSlot.Cjk -> state.cjkAxes
        MixSlot.Latin -> state.latinAxes
        MixSlot.Digit -> state.digitAxes
    }

private fun staticWeights(font: FontItem): List<Int> = font.weights
    .filterNot { it == "variable" }
    .map(::roleWeight)
    .distinct()
    .sorted()

private fun fixedWeight(font: FontItem): Int = staticWeights(font).firstOrNull() ?: 400

private fun normalizedWeight(font: FontItem, current: Int): Int = when {
    font.variable -> current.coerceIn(100, 900)
    staticWeights(font).size >= 2 -> staticWeights(font).minByOrNull { abs(it - current) } ?: 400
    else -> fixedWeight(font)
}

private fun capabilityLabel(font: FontItem): String = when {
    font.variable -> "可变字体"
    staticWeights(font).size >= 2 -> "${staticWeights(font).size} 档静态字重"
    else -> "固定 ${weightName(fixedWeight(font))}"
}

private fun roleWeight(role: String): Int = when (role.lowercase()) {
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

private fun axisDisplayName(tag: String): String = when (tag) {
        "wght" -> "字重"
        "wdth" -> "字宽"
        "slnt" -> "倾斜"
        "ital" -> "斜体开关"
        "opsz" -> "光学尺寸"
        "GRAD" -> "笔画等级"
        "XTRA" -> "横向扩展"
        "YTAS" -> "上升部"
        "YTDE" -> "下降部"
        "YTFI" -> "数字高度"
        "YTLC" -> "小写高度"
        "YTUC" -> "大写高度"
        else -> "自定义轴"
    }

    private fun axisValueLabel(value: Float): String = if (value % 1f == 0f) {
        value.roundToInt().toString()
    } else {
        String.format(java.util.Locale.US, "%.2f", value).trimEnd('0').trimEnd('.')
    }

    private fun weightName(weight: Int): String = when (weight) {
    in 0..149 -> "极细 100"
    in 150..249 -> "超细 200"
    in 250..349 -> "细体 300"
    in 350..449 -> "常规 400"
    in 450..549 -> "中等 500"
    in 550..649 -> "半粗 600"
    in 650..749 -> "粗体 700"
    in 750..849 -> "特粗 800"
    else -> "黑体 900"
}

private fun accentFor(seed: String): Color {
    val palette = listOf(
        Color(0xFF477AF4), Color(0xFF735EE7), Color(0xFF1AA88B), Color(0xFFE06B75),
        Color(0xFFDD8A25), Color(0xFF3C9DCE), Color(0xFF9A5DD7),
    )
    return palette[(seed.hashCode() and Int.MAX_VALUE) % palette.size]
}
