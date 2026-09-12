package io.github.xgl34222220.luoshu.ui.logs

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
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuDetailBar
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSectionHeading

private enum class LogsTab(val label: String) {
    TASKS("任务"), ISSUES("问题"), LOGS("日志"),
}

private enum class LogFilter(val label: String) {
    ALL("全部"), WARNING("警告"), ERROR("错误"),
}

private fun logMatchesFilter(line: String, filter: LogFilter): Boolean = when (filter) {
    LogFilter.ALL -> true
    LogFilter.WARNING -> line.contains("warn", true) || line.contains("警告")
    LogFilter.ERROR -> line.contains("error", true) || line.contains("failed", true) ||
        line.contains("失败") || line.contains("错误")
}

@Composable
internal fun LogsScreenCompact(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
    diagnosticState: DiagnosticExportState,
    onDiagnostic: () -> Unit,
    onBack: () -> Unit,
    controlsBottomPadding: Dp = 0.dp,
) {
    val tokens = LocalMiuixTokens.current
    val clipboard = LocalClipboardManager.current
    var tabName by rememberSaveable { mutableStateOf(LogsTab.TASKS.name) }
    var filterName by rememberSaveable { mutableStateOf(LogFilter.ALL.name) }
    var query by rememberSaveable { mutableStateOf("") }
    val taskListState = rememberLazyListState()
    val issueListState = rememberLazyListState()
    val logListState = rememberLazyListState()
    val tab = LogsTab.valueOf(tabName)
    val filter = LogFilter.valueOf(filterName)
    // Keep the raw log out of one enormous Text layout. Only visible rows are composed.
    val lines = remember(state.content) { state.content.lineSequence().withIndex().filter { it.value.isNotBlank() }.toList() }
    val visibleLines = remember(lines, filter, query) {
        lines.filter { logMatchesFilter(it.value, filter) && (query.isBlank() || it.value.contains(query.trim(), true)) }
    }
    val failed = remember(state.tasks) { state.tasks.filter { it.phase == TaskPhase.FAILED } }
    LaunchedEffect(filter, query) { logListState.scrollToItem(0) }

    Column(Modifier.fillMaxSize()) {
        LuoShuDetailBar(title = "任务与日志", onBack = onBack) {
            DiagnosticExportButton(style = style, state = diagnosticState, onClick = onDiagnostic)
            LuoShuHeaderAction(
                icon = Icons.Rounded.Refresh,
                contentDescription = "刷新任务和日志",
                onClick = actions.refresh,
                containerColor = tokens.elevatedCardBackground,
            )
        }
        LogTabSelector(tab) { tabName = it.name }
        LazyColumn(
            state = when (tab) { LogsTab.TASKS -> taskListState; LogsTab.ISSUES -> issueListState; LogsTab.LOGS -> logListState },
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(start = 20.dp, top = 16.dp, end = 20.dp, bottom = controlsBottomPadding + 28.dp),
            verticalArrangement = Arrangement.spacedBy(if (tab == LogsTab.LOGS) 8.dp else 12.dp),
        ) {
            when (tab) {
                LogsTab.TASKS -> {
                    item(key = "overview") { OverviewCard(state) }
                    item(key = "task-heading") { LuoShuSectionHeading("最近任务", "${state.tasks.size} 条记录") }
                    if (state.tasks.isEmpty()) {
                        item(key = "task-empty") {
                            EmptyState(Icons.Rounded.CheckCircle, "还没有字体任务", "扫描、导入、应用或组合字体后，进度和结果会显示在这里。")
                        }
                    } else {
                        items(state.tasks, key = { "task-${it.id}" }) { TaskCard(it) }
                    }
                }
                LogsTab.ISSUES -> {
                    item(key = "issue-summary") { IssueSummary(failed.size, state.warningCount, state.errorCount) }
                    if (failed.isEmpty() && state.errorCount == 0 && state.warningCount == 0) {
                        item(key = "issue-empty") {
                            EmptyState(Icons.Rounded.CheckCircle, "暂无问题记录", "当前任务和日志中没有失败、错误或警告记录。")
                        }
                    } else {
                        items(failed, key = { "issue-${it.id}" }) { TaskCard(it) }
                        if (state.warningCount > 0 || state.errorCount > 0) {
                            item(key = "open-issue-logs") {
                                Surface(
                                    onClick = {
                                        filterName = if (state.errorCount > 0) LogFilter.ERROR.name else LogFilter.WARNING.name
                                        query = ""
                                        tabName = LogsTab.LOGS.name
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(24.dp),
                                    color = MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = .55f),
                                ) {
                                    Row(Modifier.padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Icon(Icons.Rounded.Search, null, tint = MaterialTheme.colorScheme.onTertiaryContainer)
                                        Spacer(Modifier.width(12.dp))
                                        Column(Modifier.weight(1f)) {
                                            Text("查看相关日志", color = MaterialTheme.colorScheme.onTertiaryContainer, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                                            Text("${state.warningCount} 条警告 · ${state.errorCount} 条错误", color = MaterialTheme.colorScheme.onTertiaryContainer, fontSize = 12.sp)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                LogsTab.LOGS -> {
                    item(key = "log-summary") {
                        Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = tokens.cardBackground)) {
                            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Metric("日志", state.lineCount, MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                                    Metric("警告", state.warningCount, tokens.warning, Modifier.weight(1f))
                                    Metric("错误", state.errorCount, MaterialTheme.colorScheme.error, Modifier.weight(1f))
                                }
                                OutlinedTextField(
                                    value = query,
                                    onValueChange = { query = it },
                                    modifier = Modifier.fillMaxWidth(),
                                    placeholder = { Text("搜索任务、字体或关键字", fontSize = 13.sp) },
                                    leadingIcon = { Icon(Icons.Rounded.Search, null, modifier = Modifier.size(22.dp)) },
                                    trailingIcon = if (query.isNotEmpty()) {
                                        { IconButton(onClick = { query = "" }) { Icon(Icons.Rounded.Close, "清空搜索", modifier = Modifier.size(20.dp)) } }
                                    } else null,
                                    singleLine = true,
                                    shape = RoundedCornerShape(16.dp),
                                )
                                Row(Modifier.fillMaxWidth().selectableGroup(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    LogFilter.entries.forEach { option ->
                                        ChoiceChip(option.label, option == filter, Modifier.weight(1f)) { filterName = option.name }
                                    }
                                }
                            }
                        }
                    }
                    item(key = "log-heading") {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text("${visibleLines.size} 条记录", color = tokens.textSecondary, fontSize = 12.sp, modifier = Modifier.weight(1f))
                            TextButton(
                                onClick = { clipboard.setText(AnnotatedString(visibleLines.joinToString("\n") { it.value })) },
                                enabled = visibleLines.isNotEmpty(),
                            ) {
                                Icon(Icons.Rounded.ContentCopy, null, modifier = Modifier.size(17.dp))
                                Spacer(Modifier.width(6.dp))
                                Text(if (filter == LogFilter.ALL && query.isBlank()) "复制全部" else "复制筛选结果", fontSize = 12.sp)
                            }
                        }
                    }
                    if (visibleLines.isEmpty()) {
                        item(key = "log-empty") { EmptyState(Icons.Rounded.Search, "没有匹配的日志", "换一个关键字，或选择“全部”查看运行记录。") }
                    } else {
                        items(visibleLines, key = { "log-${it.index}" }) { line -> LogLine(line.index + 1, line.value) }
                    }
                }
            }
        }
    }
}

@Composable
private fun LogTabSelector(selected: LogsTab, onSelected: (LogsTab) -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .65f),
    ) {
        Row(Modifier.fillMaxWidth().selectableGroup().padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            LogsTab.entries.forEach { option -> ChoiceChip(option.label, option == selected, Modifier.weight(1f)) { onSelected(option) } }
        }
    }
}

@Composable
private fun ChoiceChip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(
        modifier = modifier.clip(RoundedCornerShape(14.dp)).selectable(selected = selected, role = Role.Tab, onClick = onClick),
        shape = RoundedCornerShape(14.dp),
        color = if (selected) LocalMiuixTokens.current.cardBackground else Color.Transparent,
        contentColor = if (selected) MaterialTheme.colorScheme.primary else LocalMiuixTokens.current.textSecondary,
        shadowElevation = if (selected) 1.dp else 0.dp,
    ) {
        Box(Modifier.heightIn(min = 48.dp).padding(horizontal = 8.dp, vertical = 12.dp), contentAlignment = Alignment.Center) {
            Text(label, textAlign = TextAlign.Center, fontSize = 14.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium)
        }
    }
}

@Composable
private fun OverviewCard(state: LogsUiState) {
    val tokens = LocalMiuixTokens.current
    Card(shape = RoundedCornerShape(26.dp), colors = CardDefaults.cardColors(containerColor = tokens.cardBackground)) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusIcon(if (state.activeTaskCount > 0) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle, MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        if (state.activeTaskCount > 0) "${state.activeTaskCount} 个任务正在处理" else "当前没有进行中的任务",
                        color = tokens.textPrimary, fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        if (state.rebootRequired) "字体已准备好，重启后生效" else "最近的操作结果保留在下方",
                        color = if (state.rebootRequired) MaterialTheme.colorScheme.primary else tokens.textSecondary,
                        fontSize = 12.sp, lineHeight = 18.sp,
                    )
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Metric("进行中", state.activeTaskCount, MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                Metric("已完成", state.completedTaskCount, tokens.success, Modifier.weight(1f))
                Metric("失败", state.failedTaskCount, MaterialTheme.colorScheme.error, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun IssueSummary(failedCount: Int, warningCount: Int, errorCount: Int) {
    val tokens = LocalMiuixTokens.current
    val hasIssues = failedCount > 0 || warningCount > 0 || errorCount > 0
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = tokens.cardBackground)) {
        Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
            StatusIcon(if (hasIssues) Icons.Rounded.Warning else Icons.Rounded.CheckCircle, if (hasIssues) tokens.warning else tokens.success)
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(if (failedCount > 0) "$failedCount 个任务未完成" else if (hasIssues) "有需要查看的运行记录" else "当前没有问题记录", color = tokens.textPrimary, fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold)
                Text("$warningCount 条警告 · $errorCount 条错误日志", color = tokens.textSecondary, fontSize = 12.sp, lineHeight = 18.sp)
            }
        }
    }
}

@Composable
private fun TaskCard(task: TaskCenterItem) {
    val tokens = LocalMiuixTokens.current
    var expanded by rememberSaveable(task.id) { mutableStateOf(false) }
    val color = when (task.phase) {
        TaskPhase.FAILED -> MaterialTheme.colorScheme.error
        TaskPhase.SUCCESS -> tokens.success
        TaskPhase.WAITING_REBOOT -> tokens.warning
        TaskPhase.INFO -> tokens.textSecondary
        else -> MaterialTheme.colorScheme.primary
    }
    Card(
        onClick = { expanded = !expanded },
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusIcon(taskKindIcon(task.kind), color)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(task.title, color = tokens.textPrimary, fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold)
                    if (task.timeLabel.isNotBlank()) Text(task.timeLabel, color = tokens.textSecondary, fontSize = 12.sp)
                }
                Spacer(Modifier.width(8.dp))
                Icon(if (expanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, if (expanded) "收起任务详情" else "展开任务详情", tint = tokens.textSecondary, modifier = Modifier.size(20.dp))
            }
            Text(task.message, color = tokens.textSecondary, fontSize = 13.sp, lineHeight = 20.sp, maxLines = if (expanded) Int.MAX_VALUE else 3, overflow = TextOverflow.Ellipsis)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Surface(shape = RoundedCornerShape(10.dp), color = color.copy(alpha = .09f)) {
                    Text(task.phase.label, Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = color, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
                Spacer(Modifier.weight(1f))
                if (task.active && task.progress >= 0) Text("${task.progress.coerceIn(0, 100)}%", color = color, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            }
            if (task.active) {
                if (task.progress >= 0) {
                    LinearProgressIndicator(progress = { task.progress.coerceIn(0, 100) / 100f }, modifier = Modifier.fillMaxWidth().height(5.dp).clip(RoundedCornerShape(5.dp)), color = color)
                } else {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth().height(5.dp).clip(RoundedCornerShape(5.dp)), color = color)
                }
            }
        }
    }
}

@Composable
private fun LogLine(number: Int, text: String) {
    val tokens = LocalMiuixTokens.current
    val color = when {
        logMatchesFilter(text, LogFilter.ERROR) -> MaterialTheme.colorScheme.error
        logMatchesFilter(text, LogFilter.WARNING) -> tokens.warning
        else -> tokens.textPrimary
    }
    Surface(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), color = tokens.cardBackground) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 12.dp), verticalAlignment = Alignment.Top) {
            Text(number.toString(), modifier = Modifier.width(34.dp), color = tokens.textSecondary, fontSize = 11.sp, lineHeight = 19.sp, fontFamily = FontFamily.Monospace)
            SelectionContainer(Modifier.weight(1f)) {
                Text(text, color = color, fontFamily = FontFamily.Monospace, fontSize = 12.sp, lineHeight = 19.sp)
            }
        }
    }
}

@Composable
private fun Metric(label: String, value: Int, color: Color, modifier: Modifier) {
    Surface(modifier = modifier, shape = RoundedCornerShape(16.dp), color = color.copy(alpha = .07f)) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(value.toString(), color = color, fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.SemiBold)
            Text(label, color = LocalMiuixTokens.current.textSecondary, fontSize = 12.sp)
        }
    }
}

@Composable
private fun StatusIcon(icon: ImageVector, color: Color) {
    Surface(modifier = Modifier.size(44.dp), shape = RoundedCornerShape(16.dp), color = color.copy(alpha = .09f)) {
        Box(contentAlignment = Alignment.Center) { Icon(icon, null, tint = color, modifier = Modifier.size(23.dp)) }
    }
}

@Composable
private fun EmptyState(icon: ImageVector, title: String, message: String) {
    val tokens = LocalMiuixTokens.current
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = tokens.cardBackground)) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            StatusIcon(icon, MaterialTheme.colorScheme.primary)
            Text(title, color = tokens.textPrimary, fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center)
            Text(message, color = tokens.textSecondary, fontSize = 13.sp, lineHeight = 20.sp, textAlign = TextAlign.Center)
        }
    }
}

private fun taskKindIcon(kind: TaskKind): ImageVector = when (kind) {
    TaskKind.SCAN -> Icons.Rounded.Search
    TaskKind.IMPORT -> Icons.Rounded.Add
    TaskKind.APPLY -> Icons.Rounded.FontDownload
    TaskKind.RESTORE -> Icons.Rounded.Refresh
    TaskKind.MIX -> Icons.Rounded.Layers
    TaskKind.DELETE -> Icons.Rounded.Delete
    TaskKind.REBOOT -> Icons.Rounded.RestartAlt
    TaskKind.DIAGNOSTIC -> Icons.Rounded.Description
}
