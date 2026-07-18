package io.github.xgl34222220.luoshu

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.launch

private enum class AppPage(val title: String, val subtitle: String, val mark: String) {
    Overview("概览", "原生状态", "概"),
    Workbench("工作台", "现有 WebUI", "工"),
    Logs("日志", "原生诊断", "志"),
}

private val LuoShuLight = lightColorScheme(
    primary = Color(0xFF4D78F6),
    onPrimary = Color.White,
    secondary = Color(0xFF7658D9),
    tertiary = Color(0xFFF07A54),
    background = Color(0xFFF5F7FC),
    surface = Color(0xFFFFFFFF),
    surfaceVariant = Color(0xFFEEF2FA),
    onSurface = Color(0xFF172033),
    onSurfaceVariant = Color(0xFF667086),
)

private val LuoShuDark = darkColorScheme(
    primary = Color(0xFF9DB4FF),
    onPrimary = Color(0xFF0D2C72),
    secondary = Color(0xFFC8B8FF),
    tertiary = Color(0xFFFFB59E),
    background = Color(0xFF10131B),
    surface = Color(0xFF171B25),
    surfaceVariant = Color(0xFF222837),
    onSurface = Color(0xFFF1F3FA),
    onSurfaceVariant = Color(0xFFAEB7CB),
)

@Composable
internal fun LuoShuApp(viewModel: LuoShuViewModel = viewModel()) {
    val pagerState = rememberPagerState(pageCount = { AppPage.entries.size })
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        viewModel.refresh()
    }

    MaterialTheme(colorScheme = if (androidx.compose.foundation.isSystemInDarkTheme()) LuoShuDark else LuoShuLight) {
        Scaffold(
            containerColor = MaterialTheme.colorScheme.background,
            bottomBar = {
                HybridBottomBar(
                    selected = AppPage.entries[pagerState.currentPage],
                    onSelect = { page -> scope.launch { pagerState.animateScrollToPage(page.ordinal) } },
                )
            },
        ) { innerPadding ->
            HorizontalPager(
                state = pagerState,
                userScrollEnabled = false,
                beyondViewportPageCount = 2,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
            ) { index ->
                when (AppPage.entries[index]) {
                    AppPage.Overview -> OverviewPage(
                        snapshot = viewModel.snapshot,
                        onRefresh = viewModel::refresh,
                        onOpenWorkbench = { scope.launch { pagerState.animateScrollToPage(AppPage.Workbench.ordinal) } },
                    )
                    AppPage.Workbench -> HybridWebView(modifier = Modifier.fillMaxSize())
                    AppPage.Logs -> LogsPage(logs = viewModel.logs, onRefresh = viewModel::refreshLogs)
                }
            }
        }
    }
}

@Composable
private fun OverviewPage(
    snapshot: ModuleSnapshot,
    onRefresh: () -> Unit,
    onOpenWorkbench: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Surface(
                shape = RoundedCornerShape(30.dp),
                color = Color.Transparent,
                shadowElevation = 10.dp,
            ) {
                Column(
                    modifier = Modifier
                        .background(
                            Brush.linearGradient(
                                listOf(Color(0xFF4D82F7), Color(0xFF685EE7), Color(0xFF8D5BD5)),
                            ),
                        )
                        .padding(20.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            modifier = Modifier.size(54.dp),
                            shape = RoundedCornerShape(18.dp),
                            color = Color.White.copy(alpha = 0.18f),
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text("洛", color = Color.White, fontWeight = FontWeight.Black, fontSize = 24.sp)
                            }
                        }
                        Spacer(Modifier.width(13.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text("洛书 Hybrid", color = Color.White, fontWeight = FontWeight.Black, fontSize = 23.sp)
                            Text("原生控制台 + 字体工作台 WebUI", color = Color.White.copy(alpha = 0.78f), fontSize = 12.sp)
                        }
                        if (snapshot.loading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(22.dp),
                                color = Color.White,
                                strokeWidth = 2.5.dp,
                            )
                        }
                    }
                    Spacer(Modifier.height(18.dp))
                    Text(
                        snapshot.version,
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp,
                    )
                    Text(
                        if (snapshot.installed) "模块已连接，底层引擎继续由 /data/adb/modules/LuoShu 提供" else "未检测到洛书模块",
                        color = Color.White.copy(alpha = 0.78f),
                        fontSize = 11.sp,
                        lineHeight = 17.sp,
                    )
                }
            }
        }

        if (snapshot.error.isNotBlank()) {
            item {
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                ) {
                    Column(Modifier.padding(15.dp)) {
                        Text("连接异常", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onErrorContainer)
                        Text(snapshot.error, fontSize = 12.sp, color = MaterialTheme.colorScheme.onErrorContainer)
                    }
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                NativeInfoCard(
                    modifier = Modifier.weight(1f),
                    mark = "R",
                    label = "Root 授权",
                    value = if (snapshot.rootGranted) "已授权" else "未授权",
                    detail = snapshot.rootManager,
                    positive = snapshot.rootGranted,
                )
                NativeInfoCard(
                    modifier = Modifier.weight(1f),
                    mark = "M",
                    label = "模块状态",
                    value = if (snapshot.installed) "已连接" else "未安装",
                    detail = "Code ${snapshot.versionCode}",
                    positive = snapshot.installed,
                )
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                NativeInfoCard(
                    modifier = Modifier.weight(1f),
                    mark = "挂",
                    label = "挂载环境",
                    value = snapshot.mountEngine,
                    detail = "自动识别",
                    positive = true,
                )
                NativeInfoCard(
                    modifier = Modifier.weight(1f),
                    mark = "字",
                    label = "当前文字字体",
                    value = snapshot.activeLabel,
                    detail = snapshot.activeFont,
                    positive = snapshot.activeFont != "default",
                )
            }
        }

        item {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = MaterialTheme.colorScheme.surface,
                shadowElevation = 2.dp,
            ) {
                Column(Modifier.padding(17.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(shape = CircleShape, color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)) {
                            Text("进", modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                        Spacer(Modifier.width(11.dp))
                        Column(Modifier.weight(1f)) {
                            Text("后台任务", fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            Text(snapshot.taskState, color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(
                        snapshot.taskMessage,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                        lineHeight = 18.sp,
                    )
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onOpenWorkbench,
                    enabled = snapshot.rootGranted && snapshot.installed,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Text("打开字体工作台", fontWeight = FontWeight.Bold)
                }
                OutlinedButton(
                    onClick = onRefresh,
                    modifier = Modifier.height(50.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Text("刷新")
                }
            }
        }

        item {
            Text(
                "Hybrid Alpha1 先原生化状态、导航和日志；组合、多轴、对比与健康评分继续复用已经验证的 v14.2 Alpha3 WebUI。",
                modifier = Modifier.padding(horizontal = 5.dp, vertical = 3.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                lineHeight = 17.sp,
            )
        }
    }
}

@Composable
private fun NativeInfoCard(
    modifier: Modifier,
    mark: String,
    label: String,
    value: String,
    detail: String,
    positive: Boolean,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(22.dp),
        color = MaterialTheme.colorScheme.surface,
        shadowElevation = 2.dp,
    ) {
        Column(Modifier.padding(15.dp)) {
            Surface(
                shape = RoundedCornerShape(11.dp),
                color = if (positive) MaterialTheme.colorScheme.primary.copy(alpha = 0.12f) else MaterialTheme.colorScheme.surfaceVariant,
            ) {
                Text(
                    mark,
                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 6.dp),
                    color = if (positive) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontWeight = FontWeight.Black,
                    fontSize = 11.sp,
                )
            }
            Spacer(Modifier.height(13.dp))
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
            Text(
                value,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp,
            )
            Text(detail, maxLines = 1, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
        }
    }
}

@Composable
private fun LogsPage(logs: String, onRefresh: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("运行日志", fontWeight = FontWeight.Black, fontSize = 23.sp)
                Text("直接读取模块 fontswitch.log", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
            OutlinedButton(onClick = onRefresh, shape = RoundedCornerShape(15.dp)) {
                Text("刷新")
            }
        }
        Surface(
            modifier = Modifier.fillMaxSize(),
            shape = RoundedCornerShape(24.dp),
            color = MaterialTheme.colorScheme.surface,
            shadowElevation = 2.dp,
        ) {
            SelectionContainer {
                Text(
                    logs,
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
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
private fun HybridBottomBar(selected: AppPage, onSelect: (AppPage) -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
        shape = RoundedCornerShape(27.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.97f),
        shadowElevation = 12.dp,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(7.dp),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
        ) {
            AppPage.entries.forEach { page ->
                val active = page == selected
                val background by animateColorAsState(
                    if (active) MaterialTheme.colorScheme.primary.copy(alpha = 0.13f) else Color.Transparent,
                    label = "navBackground",
                )
                val height by animateDpAsState(if (active) 52.dp else 48.dp, label = "navHeight")
                Row(
                    modifier = Modifier
                        .weight(1f)
                        .height(height)
                        .clip(RoundedCornerShape(19.dp))
                        .background(background)
                        .clickable { onSelect(page) }
                        .padding(horizontal = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
                    Surface(
                        shape = RoundedCornerShape(10.dp),
                        color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                    ) {
                        Text(
                            page.mark,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp),
                            color = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                    if (active) {
                        Spacer(Modifier.width(7.dp))
                        Column {
                            Text(page.title, fontWeight = FontWeight.Bold, fontSize = 11.sp, color = MaterialTheme.colorScheme.primary)
                            Text(page.subtitle, fontSize = 8.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }
}
