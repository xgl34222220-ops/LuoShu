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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBack
import androidx.compose.material.icons.rounded.Build
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Extension
import androidx.compose.material.icons.rounded.Home
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.TextFields
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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

private enum class AppPage { Overview, Workbench, Logs }

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

@Composable
internal fun LuoShuApp(viewModel: LuoShuViewModel = viewModel()) {
    var page by rememberSaveable { mutableStateOf(AppPage.Overview) }
    var workbenchReload by remember { mutableIntStateOf(0) }

    LaunchedEffect(Unit) { viewModel.refresh() }
    BackHandler(enabled = page == AppPage.Workbench) { page = AppPage.Overview }

    MaterialTheme(
        colorScheme = if (androidx.compose.foundation.isSystemInDarkTheme()) LuoShuDark else LuoShuLight,
    ) {
        when (page) {
            AppPage.Workbench -> WorkbenchHost(
                reloadKey = workbenchReload,
                onBack = { page = AppPage.Overview },
                onReload = { workbenchReload += 1 },
            )
            AppPage.Overview, AppPage.Logs -> NativeShell(
                page = page,
                snapshot = viewModel.snapshot,
                logs = viewModel.logs,
                onPage = { page = it },
                onRefresh = viewModel::refresh,
                onRefreshLogs = viewModel::refreshLogs,
                onOpenWorkbench = { page = AppPage.Workbench },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NativeShell(
    page: AppPage,
    snapshot: ModuleSnapshot,
    logs: String,
    onPage: (AppPage) -> Unit,
    onRefresh: () -> Unit,
    onRefreshLogs: () -> Unit,
    onOpenWorkbench: () -> Unit,
) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(if (page == AppPage.Overview) "洛书" else "运行日志", fontWeight = FontWeight.Black)
                        Text(
                            if (page == AppPage.Overview) "字体引擎控制台" else "模块诊断记录",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = if (page == AppPage.Overview) onRefresh else onRefreshLogs) {
                        Icon(Icons.Rounded.Refresh, contentDescription = "刷新")
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp) {
                NavigationBarItem(
                    selected = page == AppPage.Overview,
                    onClick = { onPage(AppPage.Overview) },
                    icon = { Icon(Icons.Rounded.Home, contentDescription = null) },
                    label = { Text("概览") },
                )
                NavigationBarItem(
                    selected = false,
                    onClick = onOpenWorkbench,
                    icon = { Icon(Icons.Rounded.Build, contentDescription = null) },
                    label = { Text("工作台") },
                )
                NavigationBarItem(
                    selected = page == AppPage.Logs,
                    onClick = { onPage(AppPage.Logs) },
                    icon = { Icon(Icons.Rounded.Description, contentDescription = null) },
                    label = { Text("日志") },
                )
            }
        },
    ) { padding ->
        when (page) {
            AppPage.Overview -> OverviewPage(
                snapshot = snapshot,
                onRefresh = onRefresh,
                onOpenWorkbench = onOpenWorkbench,
                modifier = Modifier.padding(padding),
            )
            AppPage.Logs -> LogsPage(logs, Modifier.padding(padding))
            AppPage.Workbench -> Unit
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun WorkbenchHost(reloadKey: Int, onBack: () -> Unit, onReload: () -> Unit) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            CenterAlignedTopAppBar(
                title = {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("字体工作台", fontWeight = FontWeight.Black, fontSize = 17.sp)
                        Text("组合 · 多轴 · 对比 · 健康", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Rounded.ArrowBack, contentDescription = "返回")
                    }
                },
                actions = {
                    IconButton(onClick = onReload) {
                        Icon(Icons.Rounded.Refresh, contentDescription = "重新载入")
                    }
                },
            )
        },
    ) { padding ->
        HybridWebView(
            reloadKey = reloadKey,
            modifier = Modifier.fillMaxSize().padding(padding),
        )
    }
}

@Composable
private fun OverviewPage(
    snapshot: ModuleSnapshot,
    onRefresh: () -> Unit,
    onOpenWorkbench: () -> Unit,
    modifier: Modifier = Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Surface(
                shape = RoundedCornerShape(28.dp),
                color = Color.Transparent,
                shadowElevation = 4.dp,
            ) {
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
                        if (snapshot.activeFont == "mix") "中文为完整基底，英文与数字按组合替换" else snapshot.activeFont,
                        color = Color.White.copy(alpha = 0.75f),
                        fontSize = 11.sp,
                    )
                }
            }
        }

        if (snapshot.error.isNotBlank()) item {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                shape = RoundedCornerShape(20.dp),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("连接异常", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onErrorContainer)
                    Text(snapshot.error, fontSize = 12.sp, color = MaterialTheme.colorScheme.onErrorContainer)
                }
            }
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
                StatusCard(Modifier.weight(1f), Icons.Rounded.Build, "挂载引擎", snapshot.mountEngine, "自动识别")
            }
        }

        item {
            Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(Modifier.padding(17.dp)) {
                    Text("后台任务", fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Spacer(Modifier.height(5.dp))
                    Text(snapshot.taskState, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                    Text(snapshot.taskMessage, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp, lineHeight = 18.sp)
                }
            }
        }

        item {
            Button(
                onClick = onOpenWorkbench,
                enabled = snapshot.rootGranted && snapshot.installed,
                modifier = Modifier.fillMaxWidth().height(54.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                Icon(Icons.Rounded.Build, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("进入字体工作台", fontWeight = FontWeight.Bold)
            }
        }

        item {
            Text(
                "Hybrid Alpha2：原生页面不再与 WebUI 重复叠加；工作台使用独立全屏宿主。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                lineHeight = 17.sp,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}

@Composable
private fun StatusCard(modifier: Modifier, icon: ImageVector, label: String, value: String, detail: String) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(21.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(Modifier.padding(15.dp)) {
            Surface(shape = RoundedCornerShape(12.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = 0.11f)) {
                Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(8.dp).size(18.dp))
            }
            Spacer(Modifier.height(12.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
            Text(value, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Text(detail, maxLines = 1, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
        }
    }
}

@Composable
private fun LogsPage(logs: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxSize().padding(16.dp),
        shape = RoundedCornerShape(22.dp),
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
