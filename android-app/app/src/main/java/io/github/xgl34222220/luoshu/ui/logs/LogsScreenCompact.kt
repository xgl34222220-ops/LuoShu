package io.github.xgl34222220.luoshu.ui.logs

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Refresh
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens

private enum class LogsTab(val label: String) {
    TASKS("任务"),
    ISSUES("问题"),
    LOGS("日志"),
}

@Composable
internal fun LogsScreenCompact(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
    diagnosticState: DiagnosticExportState,
    onDiagnostic: () -> Unit,
) {
    val miuix = style == UiStyle.MIUIX
    val tokens = LocalMiuixTokens.current
    val cardColor = if (miuix) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow
    val elevatedColor = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh
    val textPrimary = if (miuix) tokens.textPrimary else MaterialTheme.colorScheme.onSurface
    val textSecondary = if (miuix) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    var tab by remember { mutableStateOf(LogsTab.TASKS) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        "TASK CENTER",
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.2.sp,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "任务中心",
                        color = textPrimary,
                        fontSize = 34.sp,
                        lineHeight = 39.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        "任务、问题和原始日志分开查看",
                        color = textSecondary,
                        fontSize = 12.sp,
                    )
                }
                DiagnosticExportButton(
                    style = style,
                    state = diagnosticState,
                    onClick = onDiagnostic,
                )
                Spacer(Modifier.size(8.dp))
                LuoShuHeaderAction(
                    icon = Icons.Rounded.Refresh,
                    contentDescription = "刷新任务和日志",
                    onClick = actions.refresh,
                    containerColor = elevatedColor,
                )
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                LogsTab.entries.forEach { option ->
                    Surface(
                        modifier = Modifier
                            .weight(1f)
                            .clickable { tab = option },
                        shape = RoundedCornerShape(16.dp),
                        color = if (tab == option) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.surfaceContainerHigh
                        },
                    ) {
                        Text(
                            option.label,
                            modifier = Modifier.padding(vertical = 11.dp),
                            color = if (tab == option) {
                                MaterialTheme.colorScheme.onPrimary
                            } else {
                                MaterialTheme.colorScheme.onSurface
                            },
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                }
            }
        }

        when (tab) {
            LogsTab.TASKS -> {
                item {
                    OverviewCard(
                        state = state,
                        cardColor = cardColor,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                }
                if (state.tasks.isEmpty()) {
                    item {
                        EmptyState(
                            icon = Icons.Rounded.CheckCircle,
                            title = "当前没有任务记录",
                            message = "扫描、导入、应用或组合字体后会显示在这里",
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
                } else {
                    items(state.tasks, key = { it.id }) { task ->
                        TaskCard(
                            task = task,
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
                }
            }

            LogsTab.ISSUES -> {
                val failed = state.tasks.filter { it.phase == TaskPhase.FAILED }
                item {
                    IssueSummary(
                        failedCount = failed.size,
                        warningCount = state.warningCount,
                        cardColor = cardColor,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                }
                if (failed.isEmpty() && state.errorCount == 0 && state.warningCount == 0) {
                    item {
                        EmptyState(
                            icon = Icons.Rounded.CheckCircle,
                            title = "没有发现需要处理的问题",
                            message = "当前任务与日志中没有失败或警告记录",
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
                } else {
                    items(failed, key = { "issue-${it.id}" }) { task ->
                        TaskCard(
                            task = task,
                            cardColor = cardColor,
                            textPrimary = textPrimary,
                            textSecondary = textSecondary,
                        )
                    }
                    if (failed.isEmpty()) {
                        item {
                            Surface(
                                shape = RoundedCornerShape(20.dp),
                                color = MaterialTheme.colorScheme.tertiaryContainer,
                            ) {
                                Text(
                                    "存在 ${state.warningCount} 条警告或 ${state.errorCount} 条错误日志，请切换到“日志”查看原始记录。",
                                    modifier = Modifier.fillMaxWidth().padding(15.dp),
                                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                                    fontSize = 12.sp,
                                )
                            }
                        }
                    }
                }
            }

            LogsTab.LOGS -> {
                item {
                    LogSummary(
                        state = state,
                        cardColor = cardColor,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                }
                item {
                    Card(
                        shape = RoundedCornerShape(22.dp),
                        colors = CardDefaults.cardColors(containerColor = cardColor),
                    ) {
                        SelectionContainer {
                            Text(
                                state.content,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 260.dp)
                                    .padding(15.dp),
                                color = textPrimary,
                                fontFamily = FontFamily.Monospace,
                                fontSize = 11.sp,
                                lineHeight = 16.sp,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OverviewCard(
    state: LogsUiState,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Column(Modifier.padding(17.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                LuoShuGlyph(
                    imageVector = if (state.activeTaskCount > 0) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    size = LuoShuIconTokens.StatusGlyph,
                    opticalScale = if (state.activeTaskCount > 0) 1f else .98f,
                    tint = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.size(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (state.activeTaskCount > 0) "${state.activeTaskCount} 个任务正在处理" else "当前任务队列空闲",
                        color = textPrimary,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        if (state.rebootRequired) "字体已准备完成，等待完整重启" else "后台状态会在进入页面时自动同步",
                        color = if (state.rebootRequired) MaterialTheme.colorScheme.primary else textSecondary,
                        fontSize = 11.sp,
                    )
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metric("进行中", state.activeTaskCount, MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                Metric("已完成", state.completedTaskCount, Color(0xFF21966C), Modifier.weight(1f))
                Metric("失败", state.failedTaskCount, MaterialTheme.colorScheme.error, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun IssueSummary(
    failedCount: Int,
    warningCount: Int,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Row(Modifier.fillMaxWidth().padding(17.dp), verticalAlignment = Alignment.CenterVertically) {
            LuoShuGlyph(
                imageVector = if (failedCount > 0) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                contentDescription = null,
                size = LuoShuIconTokens.StatusGlyph,
                opticalScale = if (failedCount > 0) .96f else .98f,
                tint = if (failedCount > 0) MaterialTheme.colorScheme.error else Color(0xFF21966C),
            )
            Spacer(Modifier.size(12.dp))
            Column {
                Text(
                    if (failedCount > 0) "$failedCount 个失败任务需要处理" else "没有失败任务",
                    color = textPrimary,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Black,
                )
                Text("$warningCount 条警告记录", color = textSecondary, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun TaskCard(
    task: TaskCenterItem,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    val color = when (task.phase) {
        TaskPhase.FAILED -> MaterialTheme.colorScheme.error
        TaskPhase.SUCCESS -> Color(0xFF21966C)
        TaskPhase.WAITING_REBOOT -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.primary
    }
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Column(Modifier.padding(15.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(42.dp),
                    shape = RoundedCornerShape(15.dp),
                    color = color.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        LuoShuGlyph(
                            imageVector = if (task.phase == TaskPhase.FAILED) Icons.Rounded.Warning else Icons.Rounded.Description,
                            contentDescription = null,
                            size = LuoShuIconTokens.LeadingGlyph,
                            opticalScale = .96f,
                            tint = color,
                        )
                    }
                }
                Spacer(Modifier.size(11.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        task.title,
                        color = textPrimary,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        task.message,
                        color = textSecondary,
                        fontSize = 11.sp,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Spacer(Modifier.size(8.dp))
                Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .11f)) {
                    Text(
                        task.phase.label,
                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
                        color = color,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black,
                    )
                }
            }
            if (task.active && task.progress >= 0) {
                Spacer(Modifier.height(11.dp))
                LinearProgressIndicator(
                    progress = { task.progress.coerceIn(0, 100) / 100f },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                )
            }
            if (task.timeLabel.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(task.timeLabel, color = textSecondary, fontSize = 10.sp)
            }
        }
    }
}

@Composable
private fun LogSummary(
    state: LogsUiState,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Metric("日志", state.lineCount, MaterialTheme.colorScheme.primary, Modifier.weight(1f))
            Metric("警告", state.warningCount, MaterialTheme.colorScheme.tertiary, Modifier.weight(1f))
            Metric("错误", state.errorCount, MaterialTheme.colorScheme.error, Modifier.weight(1f))
        }
    }
}

@Composable
private fun Metric(label: String, value: Int, color: Color, modifier: Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(17.dp), color = color.copy(alpha = .10f)) {
        Column(Modifier.padding(horizontal = 11.dp, vertical = 10.dp)) {
            Text(value.toString(), color = color, fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        }
    }
}

@Composable
private fun EmptyState(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    message: String,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    Card(
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(38.dp))
            Spacer(Modifier.height(10.dp))
            Text(title, color = textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text(message, color = textSecondary, fontSize = 11.sp)
        }
    }
}
