package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.LinearProgressIndicator
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.basic.TextButton
import top.yukonga.miuix.kmp.theme.MiuixTheme

private enum class MiuixLogsTab(val label: String) {
    TASKS("任务"),
    ISSUES("问题"),
    LOGS("日志"),
}

@Composable
internal fun LogsScreenMiuix(
    state: LogsUiState,
    actions: LogsActions,
    diagnosticState: DiagnosticExportState,
    onDiagnostic: () -> Unit,
    onClose: (() -> Unit)? = null,
) {
    val colors = MiuixTheme.colorScheme
    var tab by remember { mutableStateOf(MiuixLogsTab.TASKS) }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background),
        contentPadding = PaddingValues(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 116.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (onClose != null) {
                    Button(onClick = onClose) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                            contentDescription = null,
                            modifier = Modifier.size(21.dp),
                        )
                    }
                    Spacer(Modifier.width(10.dp))
                }
                Column(Modifier.weight(1f)) {
                    Text(
                        text = "任务中心",
                        fontSize = 30.sp,
                        fontWeight = FontWeight.Bold,
                        color = colors.onBackground,
                    )
                    Text(
                        text = "任务、问题和原始日志",
                        fontSize = 13.sp,
                        color = colors.onSurfaceSecondary,
                    )
                }
                DiagnosticExportButtonMiuix(
                    state = diagnosticState,
                    onClick = onDiagnostic,
                )
                Spacer(Modifier.width(8.dp))
                Button(onClick = actions.refresh) {
                    Icon(
                        imageVector = Icons.Rounded.Refresh,
                        contentDescription = null,
                        modifier = Modifier.size(21.dp),
                    )
                }
            }
        }

        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                MiuixLogsTab.entries.forEach { option ->
                    if (tab == option) {
                        Button(onClick = { tab = option }) {
                            Text(option.label, fontWeight = FontWeight.Bold)
                        }
                    } else {
                        TextButton(
                            text = option.label,
                            onClick = { tab = option },
                        )
                    }
                }
            }
        }

        when (tab) {
            MiuixLogsTab.TASKS -> {
                item { MiuixTaskOverview(state) }
                if (state.tasks.isEmpty()) {
                    item {
                        MiuixLogsEmptyState(
                            icon = Icons.Rounded.CheckCircle,
                            title = "当前没有任务记录",
                            message = "扫描、导入、应用或组合字体后会显示在这里",
                        )
                    }
                } else {
                    items(state.tasks, key = { it.id }) { task ->
                        MiuixTaskCard(task)
                    }
                }
            }

            MiuixLogsTab.ISSUES -> {
                val failed = state.tasks.filter { it.phase == TaskPhase.FAILED }
                item { MiuixIssueOverview(state, failed.size) }
                if (failed.isEmpty() && state.errorCount == 0 && state.warningCount == 0) {
                    item {
                        MiuixLogsEmptyState(
                            icon = Icons.Rounded.CheckCircle,
                            title = "没有发现需要处理的问题",
                            message = "当前任务与日志中没有失败或警告记录",
                        )
                    }
                } else {
                    items(failed, key = { "miuix-issue-${it.id}" }) { task ->
                        MiuixTaskCard(task)
                    }
                    if (failed.isEmpty()) {
                        item {
                            Card(modifier = Modifier.fillMaxWidth()) {
                                BasicComponent(
                                    title = "原始日志中存在异常记录",
                                    summary = "${state.warningCount} 条警告 · ${state.errorCount} 条错误\n切换到日志页查看完整内容",
                                    startAction = { MiuixLogsIcon(Icons.Rounded.Warning, colors.error) },
                                )
                            }
                        }
                    }
                }
            }

            MiuixLogsTab.LOGS -> {
                item { MiuixLogOverview(state) }
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        BasicComponent(
                            title = "原始日志",
                            summary = "支持长按选择和复制，内容不会在界面中改写",
                            startAction = { MiuixLogsIcon(Icons.Rounded.Description, colors.primary) },
                        )
                        SelectionContainer {
                            Text(
                                text = state.content,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 280.dp)
                                    .padding(horizontal = 16.dp, vertical = 14.dp),
                                color = colors.onBackground,
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
private fun MiuixTaskOverview(state: LogsUiState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = if (state.activeTaskCount > 0) {
                "${state.activeTaskCount} 个任务正在处理"
            } else {
                "当前任务队列空闲"
            },
            summary = if (state.rebootRequired) {
                "字体已经准备完成，等待一次完整重启"
            } else {
                "进入页面时自动同步后台任务状态"
            },
            startAction = {
                MiuixLogsIcon(
                    icon = if (state.activeTaskCount > 0) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                    tint = MiuixTheme.colorScheme.primary,
                )
            },
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            MiuixMetric("进行中", state.activeTaskCount, MiuixTheme.colorScheme.primary, Modifier.weight(1f))
            MiuixMetric("已完成", state.completedTaskCount, Color(0xFF21966C), Modifier.weight(1f))
            MiuixMetric("失败", state.failedTaskCount, MiuixTheme.colorScheme.error, Modifier.weight(1f))
        }
    }
}

@Composable
private fun MiuixIssueOverview(state: LogsUiState, failedCount: Int) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = if (failedCount > 0) "$failedCount 个失败任务需要处理" else "没有失败任务",
            summary = "${state.warningCount} 条警告 · ${state.errorCount} 条错误日志",
            startAction = {
                MiuixLogsIcon(
                    icon = if (failedCount > 0) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                    tint = if (failedCount > 0) MiuixTheme.colorScheme.error else Color(0xFF21966C),
                )
            },
        )
    }
}

@Composable
private fun MiuixTaskCard(task: TaskCenterItem) {
    val colors = MiuixTheme.colorScheme
    val tint = when (task.phase) {
        TaskPhase.FAILED -> colors.error
        TaskPhase.SUCCESS -> Color(0xFF21966C)
        TaskPhase.WAITING_REBOOT -> colors.tertiary
        else -> colors.primary
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = task.title,
            summary = buildString {
                append(task.message)
                if (task.timeLabel.isNotBlank()) append("\n${task.timeLabel}")
            },
            startAction = {
                MiuixLogsIcon(
                    icon = if (task.phase == TaskPhase.FAILED) Icons.Rounded.Warning else Icons.Rounded.Description,
                    tint = tint,
                )
            },
            endActions = {
                Text(
                    text = task.phase.label,
                    color = tint,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            },
        )
        if (task.active && task.progress >= 0) {
            LinearProgressIndicator(
                progress = task.progress.coerceIn(0, 100) / 100f,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }
    }
}

@Composable
private fun MiuixLogOverview(state: LogsUiState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = "日志概览",
            summary = "${state.lineCount} 行 · ${state.warningCount} 条警告 · ${state.errorCount} 条错误",
            startAction = { MiuixLogsIcon(Icons.Rounded.Description, MiuixTheme.colorScheme.primary) },
        )
    }
}

@Composable
private fun MiuixMetric(
    label: String,
    value: Int,
    color: Color,
    modifier: Modifier,
) {
    Card(modifier = modifier) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 11.dp)) {
            Text(
                text = value.toString(),
                color = color,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = label,
                color = MiuixTheme.colorScheme.onSurfaceSecondary,
                fontSize = 10.sp,
            )
        }
    }
}

@Composable
private fun MiuixLogsEmptyState(
    icon: ImageVector,
    title: String,
    message: String,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = title,
            summary = message,
            startAction = { MiuixLogsIcon(icon, MiuixTheme.colorScheme.primary) },
        )
    }
}

@Composable
private fun MiuixLogsIcon(icon: ImageVector, tint: Color) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = tint,
        modifier = Modifier.padding(end = 16.dp).size(24.dp),
    )
}
