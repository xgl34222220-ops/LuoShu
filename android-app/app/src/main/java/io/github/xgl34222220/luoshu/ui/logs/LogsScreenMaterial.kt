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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.BugReport
import androidx.compose.material.icons.rounded.CheckCircle
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun LogsScreenMaterial(state: LogsUiState, actions: LogsActions) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialLogsHeader(actions.refresh) }
        item { MaterialTaskCard(state) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MaterialLogMetric("日志行", state.lineCount.toString(), Icons.Rounded.BugReport, Modifier.weight(1f))
                MaterialLogMetric("警告", state.warningCount.toString(), Icons.Rounded.Warning, Modifier.weight(1f))
                MaterialLogMetric("错误", state.errorCount.toString(), Icons.Rounded.CheckCircle, Modifier.weight(1f))
            }
        }
        item { MaterialTerminal(state.content) }
    }
}

@Composable
private fun MaterialLogsHeader(onRefresh: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                "DIAGNOSTICS",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.2.sp,
            )
            Spacer(Modifier.height(4.dp))
            Text("运行日志", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Black)
            Text("字体任务、挂载与错误记录", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .84f),
            shadowElevation = 7.dp,
        ) {
            IconButton(onClick = onRefresh, modifier = Modifier.size(56.dp)) {
                Icon(Icons.Rounded.Refresh, contentDescription = "刷新日志")
            }
        }
    }
}

@Composable
private fun MaterialTaskCard(state: LogsUiState) {
    val running = state.taskState == "running" || state.taskState == "queued"
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(44.dp),
                    shape = MaterialTheme.shapes.large,
                    color = MaterialTheme.colorScheme.primaryContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            if (running) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (running) "后台字体任务执行中" else "后台任务状态", fontSize = 17.sp, fontWeight = FontWeight.Black)
                    Text(state.taskMessage, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
                Text(
                    if (running) "${state.taskProgress}%" else state.taskState.uppercase(),
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Black,
                    fontSize = 12.sp,
                )
            }
            if (running) {
                Spacer(Modifier.height(13.dp))
                LinearProgressIndicator(
                    progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                    modifier = Modifier.fillMaxWidth().height(7.dp),
                )
            }
        }
    }
}

@Composable
private fun MaterialLogMetric(
    label: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    modifier: Modifier,
) {
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
                        .heightIn(min = 430.dp, max = 680.dp)
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
