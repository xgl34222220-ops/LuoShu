package io.github.xgl34222220.luoshu.ui.home

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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun HomeScreenCompact(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
    trustContent: @Composable () -> Unit,
) {
    val miuix = style == UiStyle.MIUIX
    val tokens = LocalMiuixTokens.current
    val cardColor = if (miuix) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow
    val textPrimary = if (miuix) tokens.textPrimary else MaterialTheme.colorScheme.onSurface
    val textSecondary = if (miuix) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    val divider = textSecondary.copy(alpha = .12f)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 12.dp, top = 6.dp, end = 12.dp, bottom = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            HomeTitle(
                version = state.version,
                textPrimary = textPrimary,
                textSecondary = textSecondary,
            )
        }

        item {
            EngineStatusCard(
                state = state,
                actions = actions,
                textPrimary = textPrimary,
                textSecondary = textSecondary,
            )
        }

        item {
            HomeControlBar(
                actions = actions,
                enabled = !state.taskRunning,
                cardColor = cardColor,
                divider = divider,
            )
        }

        item { trustContent() }

        if (state.error.isNotBlank()) {
            item {
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.width(10.dp))
                        Text(
                            state.error,
                            modifier = Modifier.weight(1f),
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            fontSize = 12.sp,
                            lineHeight = 17.sp,
                        )
                    }
                }
            }
        }

        item { SectionTitle("设备状态", textPrimary) }

        item {
            Surface(
                shape = RoundedCornerShape(24.dp),
                color = cardColor,
                tonalElevation = 0.dp,
                shadowElevation = 0.dp,
            ) {
                Column {
                    CompactStatusRow(
                        icon = Icons.Rounded.Security,
                        title = "Root",
                        description = if (state.rootGranted) "已获得字体事务权限" else "尚未获得 Root 权限",
                        value = if (state.rootGranted) state.rootManager else "未授权",
                        healthy = state.rootGranted,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                    ThinDivider(divider)
                    CompactStatusRow(
                        icon = Icons.Rounded.Layers,
                        title = "挂载引擎",
                        description = if (state.mountHealthy) "当前挂载链工作正常" else "挂载链需要检查",
                        value = state.mountEngine,
                        healthy = state.mountHealthy,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                    ThinDivider(divider)
                    CompactStatusRow(
                        icon = Icons.Rounded.Description,
                        title = "当前任务",
                        description = state.taskMessage.ifBlank { "暂无后台字体任务" },
                        value = if (state.taskRunning) "${state.taskProgress}%" else "空闲",
                        healthy = !state.taskRunning || state.error.isBlank(),
                        showChevron = true,
                        onClick = actions.openLogs,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                    ThinDivider(divider)
                    CompactStatusRow(
                        icon = Icons.Rounded.RestartAlt,
                        title = "重启状态",
                        description = if (state.rebootRequired) "字体负载已准备，需完整重启" else "本次操作无需重启",
                        value = if (state.rebootRequired) "待重启" else "无需重启",
                        healthy = !state.rebootRequired,
                        showChevron = state.rebootRequired,
                        onClick = if (state.rebootRequired) actions.reboot else null,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                }
            }
        }

        item { SectionTitle("下一步", textPrimary) }

        item {
            val next = nextStepFor(state, actions)
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(enabled = next.enabled, onClick = next.onClick),
                shape = RoundedCornerShape(24.dp),
                color = cardColor,
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 15.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        modifier = Modifier.size(46.dp),
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(next.icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            next.title,
                            color = textPrimary,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            next.description,
                            color = textSecondary,
                            fontSize = 11.sp,
                            lineHeight = 15.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        next.actionLabel,
                        color = if (next.enabled) MaterialTheme.colorScheme.primary else textSecondary,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Icon(
                        Icons.Rounded.ChevronRight,
                        contentDescription = null,
                        tint = if (next.enabled) MaterialTheme.colorScheme.primary else textSecondary,
                        modifier = Modifier.size(20.dp),
                    )
                }
            }
        }

        item {
            SystemWeightCard(
                weight = state.systemWeight,
                actions = actions,
                cardColor = cardColor,
                textPrimary = textPrimary,
                textSecondary = textSecondary,
            )
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = actions.restoreDefault,
                    enabled = !state.taskRunning,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Text("恢复系统字体", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
                Button(
                    onClick = actions.reboot,
                    enabled = state.rebootRequired && !state.taskRunning,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Text("完整重启", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun HomeTitle(
    version: String,
    textPrimary: Color,
    textSecondary: Color,
) {
    Column(
        modifier = Modifier.fillMaxWidth().heightIn(min = 74.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            "洛书",
            color = textPrimary,
            fontSize = 27.sp,
            lineHeight = 31.sp,
            fontWeight = FontWeight.Black,
            maxLines = 1,
        )
        Text(
            "无 Hook 全局字体引擎 · $version",
            color = textSecondary,
            fontSize = 11.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun EngineStatusCard(
    state: HomeUiState,
    actions: HomeActions,
    textPrimary: Color,
    textSecondary: Color,
) {
    val healthy = state.moduleInstalled && state.rootGranted && state.mountHealthy
    val accent = if (healthy) Color(0xFF0E9F6E) else MaterialTheme.colorScheme.tertiary
    Surface(
        shape = RoundedCornerShape(25.dp),
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = .42f),
    ) {
        Box(Modifier.fillMaxWidth().heightIn(min = 182.dp)) {
            Icon(
                if (healthy) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary.copy(alpha = .16f),
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .padding(end = 4.dp)
                    .size(118.dp),
            )
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 18.dp, vertical = 16.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(9.dp).background(accent, CircleShape))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (healthy) "字体引擎运行正常" else "字体引擎需要检查",
                        color = accent,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = actions.refresh, modifier = Modifier.height(40.dp)) {
                        if (state.loading) {
                            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Rounded.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("刷新", fontSize = 12.sp)
                        }
                    }
                }
                Spacer(Modifier.height(13.dp))
                Text("当前字体", color = textSecondary, fontSize = 12.sp)
                Text(
                    state.currentFont,
                    color = textPrimary,
                    fontSize = 28.sp,
                    lineHeight = 33.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    if (state.taskRunning) state.taskMessage else "暂无后台任务",
                    color = textSecondary,
                    fontSize = 12.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                if (state.taskRunning) {
                    Spacer(Modifier.height(10.dp))
                    LinearProgressIndicator(
                        progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                        modifier = Modifier.fillMaxWidth(.68f).height(5.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun HomeControlBar(
    actions: HomeActions,
    enabled: Boolean,
    cardColor: Color,
    divider: Color,
) {
    Surface(
        shape = RoundedCornerShape(23.dp),
        color = cardColor,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().height(64.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            HomeControl(
                label = "字体库",
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.weight(1f),
                onClick = actions.openFontLibrary,
            )
            VerticalDivider(divider)
            HomeControl(
                label = "恢复",
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.weight(1f),
                enabled = enabled,
                onClick = actions.restoreDefault,
            )
            VerticalDivider(divider)
            HomeControl(
                label = "任务",
                color = MaterialTheme.colorScheme.tertiary,
                modifier = Modifier.weight(1f),
                onClick = actions.openLogs,
            )
        }
    }
}

@Composable
private fun HomeControl(
    label: String,
    color: Color,
    modifier: Modifier,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Box(
        modifier = modifier
            .height(64.dp)
            .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (enabled) color else color.copy(alpha = .38f),
            fontSize = 14.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun CompactStatusRow(
    icon: ImageVector,
    title: String,
    description: String,
    value: String,
    healthy: Boolean,
    textPrimary: Color,
    textSecondary: Color,
    showChevron: Boolean = false,
    onClick: (() -> Unit)? = null,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 70.dp)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 16.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            icon,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(25.dp),
        )
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                title,
                color = textPrimary,
                fontSize = 16.sp,
                lineHeight = 20.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
            )
            Text(
                description,
                color = textSecondary,
                fontSize = 11.sp,
                lineHeight = 15.sp,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Spacer(Modifier.width(10.dp))
        Text(
            value,
            color = if (healthy) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.End,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.width(82.dp),
        )
        if (showChevron) {
            Icon(
                Icons.Rounded.ChevronRight,
                contentDescription = null,
                tint = textSecondary,
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

@Composable
private fun SectionTitle(title: String, color: Color) {
    Text(
        title,
        modifier = Modifier.padding(start = 4.dp, top = 8.dp, bottom = 2.dp),
        color = color,
        fontSize = 22.sp,
        lineHeight = 27.sp,
        fontWeight = FontWeight.Black,
    )
}

@Composable
private fun ThinDivider(color: Color) {
    Box(Modifier.fillMaxWidth().padding(start = 54.dp).height(1.dp).background(color))
}

@Composable
private fun VerticalDivider(color: Color) {
    Box(Modifier.width(1.dp).height(28.dp).background(color))
}

private data class HomeNextStep(
    val title: String,
    val description: String,
    val actionLabel: String,
    val icon: ImageVector,
    val enabled: Boolean = true,
    val onClick: () -> Unit,
)

private fun nextStepFor(state: HomeUiState, actions: HomeActions): HomeNextStep = when {
    !state.moduleInstalled -> HomeNextStep(
        title = "连接洛书模块",
        description = "安装模块并授予 Root 权限后才能应用全局字体",
        actionLabel = "重新检查",
        icon = Icons.Rounded.Refresh,
        onClick = actions.refresh,
    )
    state.taskRunning -> HomeNextStep(
        title = "字体任务正在处理",
        description = state.taskMessage.ifBlank { "后台任务会继续运行" },
        actionLabel = "查看任务",
        icon = Icons.Rounded.Description,
        onClick = actions.openLogs,
    )
    state.rebootRequired -> HomeNextStep(
        title = "字体已经准备完成",
        description = "执行一次完整重启后应用字体并自动验证",
        actionLabel = "立即重启",
        icon = Icons.Rounded.RestartAlt,
        onClick = actions.reboot,
    )
    state.error.isNotBlank() -> HomeNextStep(
        title = "发现需要处理的问题",
        description = "打开任务中心查看错误原因与诊断信息",
        actionLabel = "查看问题",
        icon = Icons.Rounded.Warning,
        onClick = actions.openLogs,
    )
    state.currentFont.contains("系统") -> HomeNextStep(
        title = "选择一款字体",
        description = "从字体库导入、预览并应用单字体",
        actionLabel = "字体库",
        icon = Icons.Rounded.FontDownload,
        onClick = actions.openFontLibrary,
    )
    else -> HomeNextStep(
        title = "继续调整当前字体",
        description = "组合中文、英文与数字字体，或调整真实设计轴",
        actionLabel = "打开组合",
        icon = Icons.Rounded.Layers,
        onClick = actions.openFontStudio,
    )
}

@Composable
private fun SystemWeightCard(
    weight: HomeWeightUiState,
    actions: HomeActions,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Rounded.Speed,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(25.dp),
                )
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text("全局粗细微调", color = textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                    Text("不修改字体文件，可随时恢复", color = textSecondary, fontSize = 11.sp)
                }
                Text(
                    if (weight.loading) "读取中" else weight.weight.toString(),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Black,
                )
            }
            when {
                weight.loading -> {
                    Spacer(Modifier.height(12.dp))
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                }
                !weight.supported -> {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        weight.error.ifBlank { "当前系统不支持全局粗细微调" },
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 11.sp,
                    )
                }
                else -> {
                    Spacer(Modifier.height(4.dp))
                    Slider(
                        value = weight.weight.toFloat(),
                        onValueChange = actions.previewSystemWeight,
                        enabled = !weight.applying,
                        valueRange = weight.min.toFloat()..weight.max.toFloat(),
                        steps = (((weight.max - weight.min) / weight.step) - 1).coerceAtLeast(0),
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            weight.error.ifBlank { weight.message },
                            modifier = Modifier.weight(1f),
                            color = if (weight.error.isNotBlank()) MaterialTheme.colorScheme.error else textSecondary,
                            fontSize = 10.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        TextButton(onClick = actions.resetSystemWeight, enabled = !weight.applying) {
                            Text("恢复原始", fontSize = 11.sp)
                        }
                    }
                }
            }
        }
    }
}
