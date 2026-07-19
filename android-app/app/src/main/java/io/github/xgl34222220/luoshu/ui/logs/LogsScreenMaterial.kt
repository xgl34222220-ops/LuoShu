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
import androidx.compose.foundation.shape.CircleShape
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

@Composable
internal fun LogsScreenMaterial(state: LogsUiState, actions: LogsActions) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialTaskCenterHeader(actions.refresh) }
        item { MaterialTaskOverview(state) }
        item { MaterialSectionTitle("任务时间线", "最近 ${state.tasks.size} 条任务状态") }

        if (state.tasks.isEmpty()) {
            item { MaterialTaskEmpty() }
        } else {
            items(state.tasks, key = { it.id }) { task ->
                MaterialTaskCard(task)
            }
        }

        item { MaterialSectionTitle("原始日志", "用于诊断挂载、字体引擎和 Root 错误") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MaterialLogMetric("日志行", state.lineCount.toString(), Icons.Rounded.Description, Modifier.weight(1f))
                MaterialLogMetric("警告", state.warningCount.toString(), Icons.Rounded.Warning, Modifier.weight(1f))
                MaterialLogMetric("错误", state.errorCount.toString(), Icons.Rounded.CheckCircle, Modifier.weight(1f))
            }
        }
        item { MaterialTerminal(state.content) }
    }
}

@Composable
private fun MaterialTaskCenterHeader(onRefresh: () -> Unit) {
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
                letterSpacing = 2.2.sp,
            )
            Spacer(Modifier.height(4.dp))
            Text("任务中心", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Black)
            Text("扫描、导入、应用、组合与重启状态", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .84f),
            shadowElevation = 7.dp,
        ) {
            IconButton(onClick = onRefresh, modifier = Modifier.size(56.dp)) {
                Icon(Icons.Rounded.Refresh, contentDescription = "刷新任务和日志")
            }
        }
    }
}

@Composable
private fun MaterialTaskOverview(state: LogsUiState) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .86f)),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(
                        if (state.activeTaskCount > 0) "${state.activeTaskCount} 个任务正在处理" else "当前没有运行中的任务",
                        fontSize = 19.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        if (state.rebootRequired) "字体已准备完成，等待完整重启" else "任务状态会在进入页面时自动同步",
                        color = if (state.rebootRequired) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                    )
                }
                Icon(
                    if (state.activeTaskCount > 0) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(30.dp),
                )
            }
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                MaterialOverviewMetric("进行中", state.activeTaskCount, MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                MaterialOverviewMetric("已完成", state.completedTaskCount, MaterialTheme.colorScheme.tertiary, Modifier.weight(1f))
                MaterialOverviewMetric("失败", state.failedTaskCount, MaterialTheme.colorScheme.error, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MaterialOverviewMetric(label: String, value: Int, color: Color, modifier: Modifier) {
    Surface(modifier = modifier, shape = MaterialTheme.shapes.large, color = color.copy(alpha = .10f)) {
        Column(Modifier.padding(horizontal = 13.dp, vertical = 11.dp)) {
            Text(value.toString(), color = color, fontSize = 20.sp, fontWeight = FontWeight.Black)
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        }
    }
}

@Composable
private fun MaterialSectionTitle(title: String, subtitle: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 3.dp, vertical = 2.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(title, fontSize = 21.sp, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f))
        Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
    }
}

@Composable
private fun MaterialTaskCard(task: TaskCenterItem) {
    val color = taskPhaseColor(task.phase)
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .86f)),
        elevation = CardDefaults.cardElevation(defaultElevation = if (task.current) 5.dp else 1.dp),
    ) {
        Column(Modifier.padding(17.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = MaterialTheme.shapes.large,
                    color = color.copy(alpha = .12f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(taskKindIcon(task.kind), contentDescription = null, tint = color, modifier = Modifier.size(23.dp))
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(task.title, fontSize = 16.sp, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        task.message,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Spacer(Modifier.width(8.dp))
                Column(horizontalAlignment = Alignment.End) {
                    Surface(shape = CircleShape, color = color.copy(alpha = .11f)) {
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
                        Text(task.timeLabel, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
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
private fun MaterialTaskEmpty() {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(40.dp))
            Spacer(Modifier.height(12.dp))
            Text("还没有字体任务记录", fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text("执行扫描、导入、应用或组合后会显示在这里", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        }
    }
}

@Composable
private fun MaterialLogMetric(label: String, value: String, icon: ImageVector, modifier: Modifier) {
    Card(
        modifier = modifier,
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(14.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
            Spacer(Modifier.height(10.dp))
            Text(value, fontSize = 22.sp, fontWeight = FontWeight.Black)
            Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
        }
    }
}

@Composable
private fun MaterialTerminal(content: String) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = Color(0xFF111318)),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth().background(Color.White.copy(alpha = .055f)).padding(horizontal = 16.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(9.dp).background(Color(0xFFFF6B6B), CircleShape))
                Spacer(Modifier.width(6.dp))
                Box(Modifier.size(9.dp).background(Color(0xFFFFD166), CircleShape))
                Spacer(Modifier.width(6.dp))
                Box(Modifier.size(9.dp).background(Color(0xFF56E39F), CircleShape))
                Spacer(Modifier.width(12.dp))
                Text("luoshu-runtime.log", color = Color.White.copy(alpha = .72f), fontSize = 10.sp, fontFamily = FontFamily.Monospace)
            }
            SelectionContainer {
                Text(
                    text = content,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 300.dp, max = 620.dp)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp),
                    color = Color(0xFFD8DEE9),
                    fontFamily = FontFamily.Monospace,
                    fontSize = 10.sp,
                    lineHeight = 15.sp,
                )
            }
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

@Composable
private fun taskPhaseColor(phase: TaskPhase): Color = when (phase) {
    TaskPhase.FAILED -> MaterialTheme.colorScheme.error
    TaskPhase.SUCCESS -> MaterialTheme.colorScheme.tertiary
    TaskPhase.WAITING_REBOOT -> MaterialTheme.colorScheme.secondary
    TaskPhase.INFO -> MaterialTheme.colorScheme.onSurfaceVariant
    TaskPhase.QUEUED, TaskPhase.RUNNING -> MaterialTheme.colorScheme.primary
}
