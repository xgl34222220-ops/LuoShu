package io.github.xgl34222220.luoshu

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
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

private enum class AppPage(val title: String, val subtitle: String, val icon: ImageVector) {
    Overview("概览", "字体引擎状态", Icons.Rounded.Home),
    Library("字体库", "搜索、切换与管理", Icons.Rounded.List),
    Workbench("工作台", "组合、多轴、对比与健康", Icons.Rounded.Build),
    Logs("日志", "模块诊断记录", Icons.Rounded.Description),
}

private val LuoShuLight = lightColorScheme(
    primary = Color(0xFF3167E3),
    onPrimary = Color.White,
    secondary = Color(0xFF7055C8),
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
    var workbenchReload by remember { mutableIntStateOf(0) }
    var pendingApply by remember { mutableStateOf<FontItem?>(null) }
    var restoreDefault by remember { mutableStateOf(false) }
    var pendingDelete by remember { mutableStateOf<FontItem?>(null) }

    LaunchedEffect(Unit) { viewModel.refresh() }
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
                                    AppPage.Workbench -> workbenchReload += 1
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
                    onOpenWorkbench = { page = AppPage.Workbench },
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
                AppPage.Workbench -> HybridWebView(
                    reloadKey = workbenchReload,
                    modifier = Modifier.fillMaxSize().padding(padding),
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
    }
}

@Composable
private fun OverviewPage(
    viewModel: LuoShuViewModel,
    onOpenLibrary: () -> Unit,
    onOpenWorkbench: () -> Unit,
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
                                if (snapshot.installed) "模块与 App 已连接" else "等待连接洛书模块",
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
                        "字体库 ${viewModel.fonts.size} 款 · ${snapshot.mountEngine}",
                        color = Color.White.copy(alpha = 0.75f),
                        fontSize = 11.sp,
                    )
                }
            }
        }

        if (snapshot.error.isNotBlank()) item {
            ErrorCard(snapshot.error)
        }

        if (viewModel.operationMessage.isNotBlank()) item {
            OperationCard(viewModel)
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
                    modifier = Modifier.weight(1f).height(52.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Icon(Icons.Rounded.List, contentDescription = null)
                    Spacer(Modifier.width(7.dp))
                    Text("字体库", fontWeight = FontWeight.Bold)
                }
                OutlinedButton(
                    onClick = onOpenWorkbench,
                    enabled = snapshot.rootGranted && snapshot.installed,
                    modifier = Modifier.weight(1f).height(52.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Icon(Icons.Rounded.Build, contentDescription = null)
                    Spacer(Modifier.width(7.dp))
                    Text("工作台", fontWeight = FontWeight.Bold)
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = onRestoreDefault,
                    enabled = !viewModel.operationBusy,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(16.dp),
                ) { Text("恢复系统字体") }
                Button(
                    onClick = viewModel::rebootDevice,
                    enabled = viewModel.rebootRequired && !viewModel.operationBusy,
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
        if (viewModel.fontLoading || viewModel.operationBusy) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        }
        OutlinedTextField(
            value = viewModel.searchQuery,
            onValueChange = viewModel::setSearchQuery,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            singleLine = true,
            shape = RoundedCornerShape(18.dp),
            leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
            placeholder = { Text("搜索字体名称或格式") },
        )

        if (viewModel.fontError.isNotBlank()) {
            ErrorCard(viewModel.fontError, Modifier.padding(horizontal = 16.dp))
        }
        if (viewModel.operationMessage.isNotBlank()) {
            OperationCard(viewModel, Modifier.padding(horizontal = 16.dp, vertical = 6.dp))
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                SystemFontCard(
                    active = viewModel.snapshot.activeFont == "default",
                    busy = viewModel.operationBusy,
                    onRestoreDefault = onRestoreDefault,
                )
            }

            if (!viewModel.fontLoading && viewModel.filteredFonts.isEmpty()) {
                item {
                    Card(shape = RoundedCornerShape(22.dp)) {
                        Column(Modifier.fillMaxWidth().padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("没有找到字体", fontWeight = FontWeight.Bold)
                            Text(
                                if (viewModel.searchQuery.isBlank()) "请先把字体放入 /sdcard/LuoShu/fonts/" else "换一个关键词试试",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 12.sp,
                            )
                        }
                    }
                }
            }

            items(viewModel.filteredFonts, key = { it.id }) { font ->
                FontCard(
                    font = font,
                    active = viewModel.snapshot.activeFont == font.id,
                    busy = viewModel.operationBusy,
                    onApply = { onApply(font) },
                    onDelete = { onDelete(font) },
                )
            }
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
