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
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
    val elevatedColor = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh
    val textPrimary = if (miuix) tokens.textPrimary else MaterialTheme.colorScheme.onSurface
    val textSecondary = if (miuix) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    val shape = RoundedCornerShape(if (miuix) 28.dp else 24.dp)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 10.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        "FONT ENGINE",
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.2.sp,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "洛书",
                        color = textPrimary,
                        fontSize = 36.sp,
                        lineHeight = 40.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        "${if (miuix) "Miuix" else "Material"} · ${state.version}",
                        color = textSecondary,
                        fontSize = 12.sp,
                    )
                }
                HeaderAction(
                    icon = Icons.Rounded.Settings,
                    description = "设置",
                    containerColor = elevatedColor,
                    onClick = actions.openSettings,
                )
                Spacer(Modifier.width(8.dp))
                HeaderAction(
                    icon = Icons.Rounded.Refresh,
                    description = "刷新",
                    containerColor = elevatedColor,
                    loading = state.loading,
                    onClick = actions.refresh,
                )
            }
        }

        item {
            Card(
                shape = shape,
                colors = CardDefaults.cardColors(containerColor = cardColor),
                elevation = CardDefaults.cardElevation(defaultElevation = if (miuix) 5.dp else 2.dp),
            ) {
                Column(Modifier.padding(20.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier
                                .size(10.dp)
                                .background(
                                    if (state.moduleInstalled && state.rootGranted) {
                                        if (miuix) tokens.success else Color(0xFF21966C)
                                    } else {
                                        if (miuix) tokens.warning else MaterialTheme.colorScheme.tertiary
                                    },
                                    CircleShape,
                                ),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (state.moduleInstalled) "模块与字体引擎已连接" else "正在等待模块连接",
                            color = textSecondary,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                    Spacer(Modifier.height(18.dp))
                    Text("当前字体", color = textSecondary, fontSize = 12.sp)
                    Text(
                        state.currentFont,
                        color = textPrimary,
                        fontSize = 34.sp,
                        lineHeight = 39.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(16.dp))
                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                if (state.taskRunning) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(state.taskTitle, color = textPrimary, fontWeight = FontWeight.Bold)
                                Text(
                                    state.taskMessage,
                                    color = textSecondary,
                                    fontSize = 11.sp,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                            if (state.taskRunning) {
                                Text(
                                    "${state.taskProgress}%",
                                    color = MaterialTheme.colorScheme.primary,
                                    fontWeight = FontWeight.Black,
                                )
                            }
                        }
                    }
                    if (state.taskRunning) {
                        Spacer(Modifier.height(10.dp))
                        LinearProgressIndicator(
                            progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                            modifier = Modifier.fillMaxWidth().height(6.dp),
                        )
                    }
                }
            }
        }

        item { trustContent() }

        if (state.error.isNotBlank()) {
            item {
                Surface(
                    shape = RoundedCornerShape(20.dp),
                    color = MaterialTheme.colorScheme.errorContainer,
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(15.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.width(10.dp))
                        Text(
                            state.error,
                            modifier = Modifier.weight(1f),
                            color = MaterialTheme.colorScheme.onErrorContainer,
                        )
                    }
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                StatusCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Security,
                    title = "Root",
                    value = if (state.rootGranted) state.rootManager else "未授权",
                    healthy = state.rootGranted,
                    cardColor = cardColor,
                    textPrimary = textPrimary,
                    textSecondary = textSecondary,
                )
                StatusCard(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Layers,
                    title = "挂载引擎",
                    value = state.mountEngine,
                    healthy = state.mountHealthy,
                    cardColor = cardColor,
                    textPrimary = textPrimary,
                    textSecondary = textSecondary,
                )
            }
        }

        item {
            val next = nextStepFor(state, actions)
            Card(
                modifier = Modifier.fillMaxWidth().clickable(enabled = next.enabled, onClick = next.onClick),
                shape = shape,
                colors = CardDefaults.cardColors(containerColor = cardColor),
                elevation = CardDefaults.cardElevation(defaultElevation = if (miuix) 4.dp else 1.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(17.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = RoundedCornerShape(17.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(next.icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(next.title, color = textPrimary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                        Text(
                            next.description,
                            color = textSecondary,
                            fontSize = 11.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Column(horizontalAlignment = Alignment.End) {
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
                        )
                    }
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
                shape = shape,
            )
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedButton(
                    onClick = actions.restoreDefault,
                    enabled = !state.taskRunning,
                    modifier = Modifier.weight(1f).height(52.dp),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Text("恢复系统字体", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = actions.reboot,
                    enabled = state.rebootRequired && !state.taskRunning,
                    modifier = Modifier.weight(1f).height(52.dp),
                    shape = RoundedCornerShape(18.dp),
                ) {
                    Icon(Icons.Rounded.RestartAlt, contentDescription = null)
                    Spacer(Modifier.width(6.dp))
                    Text("完整重启", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
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
        description = state.taskMessage.ifBlank { "可以离开 App，后台任务会继续运行" },
        actionLabel = "查看任务",
        icon = Icons.Rounded.Description,
        onClick = actions.openLogs,
    )
    state.rebootRequired -> HomeNextStep(
        title = "字体已经准备完成",
        description = "执行一次完整重启后应用全局字体并自动验证",
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
        actionLabel = "打开字体库",
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
private fun HeaderAction(
    icon: ImageVector,
    description: String,
    containerColor: Color,
    loading: Boolean = false,
    onClick: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(17.dp),
        color = containerColor,
        tonalElevation = 2.dp,
        shadowElevation = 3.dp,
    ) {
        IconButton(onClick = onClick, modifier = Modifier.size(50.dp)) {
            if (loading) {
                CircularProgressIndicator(Modifier.size(21.dp), strokeWidth = 2.dp)
            } else {
                Icon(icon, contentDescription = description)
            }
        }
    }
}

@Composable
private fun StatusCard(
    modifier: Modifier,
    icon: ImageVector,
    title: String,
    value: String,
    healthy: Boolean,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Column(Modifier.padding(15.dp)) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(10.dp))
            Text(title, color = textSecondary, fontSize = 11.sp)
            Text(
                value,
                color = textPrimary,
                fontSize = 15.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                if (healthy) "正常" else "需要检查",
                color = if (healthy) Color(0xFF21966C) else MaterialTheme.colorScheme.error,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun SystemWeightCard(
    weight: HomeWeightUiState,
    actions: HomeActions,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
    shape: RoundedCornerShape,
) {
    Card(
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(46.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.Speed, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("全局粗细微调", color = textPrimary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                    Text("不修改字体文件，可随时恢复", color = textSecondary, fontSize = 11.sp)
                }
                Text(
                    if (weight.loading) "读取中" else weight.weight.toString(),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Black,
                )
            }
            Spacer(Modifier.height(12.dp))
            when {
                weight.loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
                !weight.supported -> Text(
                    weight.error.ifBlank { "当前系统不支持全局粗细微调" },
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 12.sp,
                )
                else -> {
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
                            fontSize = 11.sp,
                            maxLines = 2,
                        )
                        TextButton(onClick = actions.resetSystemWeight, enabled = !weight.applying) {
                            Text("恢复原始")
                        }
                    }
                }
            }
        }
    }
}
