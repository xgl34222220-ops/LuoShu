package io.github.xgl34222220.luoshu.ui.logs

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
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun LogsScreenMiuix(state: LogsUiState, actions: LogsActions) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MiuixTaskCenterHeader(actions.refresh) }
        item { MiuixTaskOverview(state) }
        item { MiuixSectionTitle("任务时间线", "最近 ${state.tasks.size} 条状态") }

        if (state.tasks.isEmpty()) {
            item { MiuixTaskEmpty() }
        } else {
            items(state.tasks, key = { it.id }) { task ->
                MiuixTaskCard(task)
            }
        }

        item { MiuixSectionTitle("原始日志", "诊断字体引擎和挂载问题") }
        item { MiuixLogSummary(state) }
        item { MiuixLogPanel(state.content) }
    }
}

@Composable
private fun MiuixTaskCenterHeader(onRefresh: () -> Unit) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                "TASK CENTER",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.4.sp,
            )
            Spacer(Modifier.height(3.dp))
            Text(
                "任务中心",
                color = tokens.textPrimary,
                fontSize = 42.sp,
                lineHeight = 47.sp,
                fontWeight = FontWeight.Black,
            )
            Text("扫描、导入、应用、组合与重启状态", color = tokens.textSecondary, fontSize = 12.sp)
        }
        Card(
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = tokens.elevatedCardBackground),
            elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
        ) {
            IconButton(onClick = onRefresh, modifier = Modifier.size(56.dp)) {
                Icon(Icons.Rounded.Refresh, contentDescription = "刷新任务和日志")
            }
        }
    }
}

@Composable
private fun MiuixTaskOverview(state: LogsUiState) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(36.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
    ) {
        Column(Modifier.padding(19.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp),
                    shape = RoundedCornerShape(19.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            if (state.activeTaskCount > 0) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (state.activeTaskCount > 0) "${state.activeTaskCount} 个任务正在处理" else "当前任务队列空闲",
                        color = tokens.textPrimary,
                        fontSize = 19.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        if (state.rebootRequired) "字体已准备完成，等待完整重启" else "进入页面时自动同步后台状态",
                        color = if (state.rebootRequired) MaterialTheme.colorScheme.primary else tokens.textSecondary,
                        fontSize = 11.sp,
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MiuixOverviewMetric("进行中", state.activeTaskCount, MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                MiuixOverviewMetric("已完成", state.completedTaskCount, tokens.success, Modifier.weight(1f))
                MiuixOverviewMetric("失败", state.failedTaskCount, MaterialTheme.colorScheme.error, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MiuixOverviewMetric(label: String, value: Int, color: Color, modifier: Modifier) {
    val tokens = LocalMiuixTokens.current
    Surface(modifier = modifier, shape = RoundedCornerShape(21.dp), color = color.copy(alpha = .10f)) {
        Column(Modifier.padding(horizontal = 13.dp, vertical = 11.dp)) {
            Text(value.toString(), color = color, fontSize = 20.sp, fontWeight = FontWeight.Black)
            Text(label, color = tokens.textSecondary, fontSize = 10.sp)
        }
    }
}

@Composable
private fun MiuixSectionTitle(title: String, subtitle: String) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(title, color = tokens.textPrimary, fontSize = 22.sp, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f))
        Text(subtitle, color = tokens.textSecondary, fontSize = 10.sp)
    }
}

@Composable
private fun MiuixTaskCard(task: TaskCenterItem) {
    val tokens = LocalMiuixTokens.current
    val color = miuixTaskPhaseColor(task.phase)
    Card(
        shape = RoundedCornerShape(32.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = if (task.current) 7.dp else 4.dp),
    ) {
        Column(Modifier.padding(horizontal = 17.dp, vertical = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = RoundedCornerShape(17.dp),
                    color = color.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(miuixTaskKindIcon(task.kind), contentDescription = null, tint = color, modifier = Modifier.size(23.dp))
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        task.title,
                        color = tokens.textPrimary,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        task.message,
                        color = tokens.textSecondary,
                        fontSize = 11.sp,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Spacer(Modifier.width(8.dp))
                Column(horizontalAlignment = Alignment.End) {
                    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .11f)) {
                        Text(
                            task.phase.label,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                            color = color,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                    if (task.timeLabel.isNotBlank()) {
                        Spacer(Modifier.height(5.dp))
                        Text(task.timeLabel, color = tokens.textSecondary, fontSize = 9.sp)
                    }
                }
            }
            if (task.active && task.progress >= 0) {
                Spacer(Modifier.height(13.dp))
                LinearProgressIndicator(
                    progress = { task.progress.coerceIn(0, 100) / 100f },
                    modifier = Modifier.fillMaxWidth().height(7.dp),
                )
            }
        }
    }
}

@Composable
private fun MiuixTaskEmpty() {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Surface(
                modifier = Modifier.size(58.dp),
                shape = RoundedCornerShape(21.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(13.dp))
            Text("还没有字体任务记录", color = tokens.textPrimary, fontSize = 20.sp, fontWeight = FontWeight.Black)
            Text("执行扫描、导入、应用或组合后会显示在这里", color = tokens.textSecondary, fontSize = 11.sp)
        }
    }
}

@Composable
private fun MiuixLogSummary(state: LogsUiState) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(32.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 7.dp)) {
            MiuixLogSummaryRow(Icons.Rounded.Description, "日志行数", state.lineCount.toString(), MaterialTheme.colorScheme.primary)
            MiuixSummaryDivider()
            MiuixLogSummaryRow(Icons.Rounded.Warning, "警告记录", state.warningCount.toString(), tokens.warning)
            MiuixSummaryDivider()
            MiuixLogSummaryRow(
                Icons.Rounded.CheckCircle,
                "错误记录",
                state.errorCount.toString(),
                if (state.errorCount == 0) tokens.success else MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun MiuixLogSummaryRow(icon: ImageVector, title: String, value: String, color: Color) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 2.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(modifier = Modifier.size(40.dp), shape = RoundedCornerShape(15.dp), color = color.copy(alpha = .11f)) {
            Box(contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(21.dp))
            }
        }
        Spacer(Modifier.width(12.dp))
        Text(title, color = tokens.textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        Text(value, color = color, fontSize = 17.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun MiuixSummaryDivider() {
    Box(
        Modifier
            .fillMaxWidth()
            .padding(start = 54.dp)
            .height(1.dp)
            .background(MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f)),
    )
}

@Composable
private fun MiuixLogPanel(content: String) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 17.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    modifier = Modifier.size(34.dp),
                    shape = RoundedCornerShape(13.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.Description, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(19.dp))
                    }
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text("运行输出", color = tokens.textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Black)
                    Text("长按可选择并复制日志文本", color = tokens.textSecondary, fontSize = 10.sp)
                }
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 14.dp)
                    .height(1.dp)
                    .background(MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f)),
            )
            SelectionContainer {
                Text(
                    text = content,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 300.dp, max = 620.dp)
                        .verticalScroll(rememberScrollState())
                        .padding(17.dp),
                    color = tokens.textSecondary,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 10.sp,
                    lineHeight = 15.sp,
                )
            }
        }
    }
}

private fun miuixTaskKindIcon(kind: TaskKind): ImageVector = when (kind) {
    TaskKind.SCAN -> Icons.Rounded.Search
    TaskKind.IMPORT -> Icons.Rounded.Add
    TaskKind.APPLY -> Icons.Rounded.FontDownload
    TaskKind.RESTORE -> Icons.Rounded.Refresh
    TaskKind.MIX -> Icons.Rounded.Layers
    TaskKind.DELETE -> Icons.Rounded.Delete
    TaskKind.REBOOT -> Icons.Rounded.RestartAlt
    TaskKind.DIAGNOSTIC -> Icons.Rounded.Description
}

@Composable
private fun miuixTaskPhaseColor(phase: TaskPhase): Color {
    val tokens = LocalMiuixTokens.current
    return when (phase) {
        TaskPhase.FAILED -> MaterialTheme.colorScheme.error
        TaskPhase.SUCCESS -> tokens.success
        TaskPhase.WAITING_REBOOT -> MaterialTheme.colorScheme.secondary
        TaskPhase.INFO -> tokens.textSecondary
        TaskPhase.QUEUED, TaskPhase.RUNNING -> MaterialTheme.colorScheme.primary
    }
}
