package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Restore
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.TaskAlt
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
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
import io.github.xgl34222220.luoshu.ui.theme.LocalLuoShuTokens

private val PagePadding = 12.dp
private val CardRadius = 17.dp
private val InnerRadius = 13.dp
private val SectionGap = 7.dp

@Composable
internal fun HomeScreenCompact(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
    trustContent: @Composable () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = PagePadding,
            top = 6.dp,
            end = PagePadding,
            bottom = 120.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(SectionGap),
    ) {
        item {
            Column(modifier = Modifier.padding(horizontal = 2.dp, vertical = 1.dp)) {
                Text(
                    text = "洛书",
                    color = tokens.textPrimary,
                    fontSize = 23.sp,
                    lineHeight = 27.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "无 Hook 全局字体引擎 · ${state.version}",
                    color = tokens.textSecondary,
                    fontSize = 10.5.sp,
                    lineHeight = 14.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        item { EngineOverview(state = state, actions = actions) }
        item {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                CompactShortcut(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.FontDownload,
                    title = "字体库",
                    subtitle = "导入与应用",
                    onClick = actions.openFontLibrary,
                )
                CompactShortcut(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Layers,
                    title = "字体组合",
                    subtitle = "中文 · 英文 · 数字",
                    onClick = actions.openFontStudio,
                )
            }
        }
        item { trustContent() }
        if (state.error.isNotBlank()) {
            item {
                CompactMessageCard(
                    icon = Icons.Rounded.Warning,
                    title = "字体引擎需要处理",
                    message = state.error,
                    tint = tokens.danger,
                    actionLabel = "查看",
                    onClick = actions.openLogs,
                )
            }
        }
        item { CompactSectionTitle("设备状态") }
        item { StatusGrid(state = state) }
        item { CompactSectionTitle("下一步") }
        item { NextStepCard(nextStepFor(state, actions)) }
        item { CompactSectionTitle("全局粗细") }
        item { SystemWeightCard(weight = state.systemWeight, actions = actions) }
    }
}

@Composable
private fun EngineOverview(state: HomeUiState, actions: HomeActions) {
    val tokens = LocalLuoShuTokens.current
    val healthy = state.moduleInstalled && state.rootGranted && state.mountHealthy
    val statusColor = when {
        state.error.isNotBlank() -> tokens.danger
        state.rebootRequired -> tokens.warning
        healthy -> tokens.success
        else -> MaterialTheme.colorScheme.primary
    }
    val statusText = when {
        state.taskRunning -> "任务执行中"
        state.rebootRequired -> "等待完整重启"
        healthy -> "字体引擎运行正常"
        else -> "正在检查运行环境"
    }
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(CardRadius),
            color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = .56f),
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .07f)),
        ) {
            Box(modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 12.dp)) {
                Column(modifier = Modifier.fillMaxWidth().padding(end = 64.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(6.dp).background(statusColor, CircleShape))
                        Spacer(Modifier.width(7.dp))
                        Text(
                            text = statusText,
                            color = statusColor,
                            fontSize = 12.sp,
                            lineHeight = 15.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = state.currentFont,
                        color = tokens.textPrimary,
                        fontSize = 19.sp,
                        lineHeight = 23.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = state.taskMessage.ifBlank { if (state.taskRunning) state.taskTitle else "暂无后台任务" },
                        color = tokens.textSecondary,
                        fontSize = 9.5.sp,
                        lineHeight = 13.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    if (state.taskRunning) {
                        Spacer(Modifier.height(7.dp))
                        LinearProgressIndicator(
                            progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                            modifier = Modifier.fillMaxWidth().height(3.dp),
                            color = statusColor,
                            trackColor = statusColor.copy(alpha = .12f),
                        )
                    }
                }
                Surface(
                    modifier = Modifier.align(Alignment.CenterEnd).size(54.dp),
                    shape = CircleShape,
                    color = statusColor.copy(alpha = .07f),
                    border = BorderStroke(2.5.dp, statusColor.copy(alpha = .68f)),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        if (state.taskRunning) {
                            Text(
                                text = "${state.taskProgress}%",
                                color = statusColor,
                                fontSize = 10.5.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        } else {
                            Icon(
                                imageVector = if (state.error.isBlank()) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                                contentDescription = null,
                                tint = statusColor,
                                modifier = Modifier.size(29.dp),
                            )
                        }
                    }
                }
            }
        }
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(InnerRadius),
            color = MaterialTheme.colorScheme.surfaceContainerLow,
            border = BorderStroke(1.dp, tokens.outline.copy(alpha = .16f)),
        ) {
            Row(modifier = Modifier.fillMaxWidth().height(40.dp)) {
                SegmentedAction(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Refresh,
                    label = "刷新",
                    tint = MaterialTheme.colorScheme.primary,
                    onClick = actions.refresh,
                    enabled = !state.loading,
                )
                VerticalRule()
                SegmentedAction(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Restore,
                    label = "恢复",
                    tint = tokens.danger,
                    onClick = actions.restoreDefault,
                    enabled = !state.taskRunning,
                )
                VerticalRule()
                SegmentedAction(
                    modifier = Modifier.weight(1f),
                    icon = if (state.rebootRequired) Icons.Rounded.RestartAlt else Icons.Rounded.Description,
                    label = if (state.rebootRequired) "重启" else "任务",
                    tint = if (state.rebootRequired) tokens.warning else MaterialTheme.colorScheme.primary,
                    onClick = if (state.rebootRequired) actions.reboot else actions.openLogs,
                )
            }
        }
    }
}

@Composable
private fun SegmentedAction(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    tint: Color,
    onClick: () -> Unit,
    enabled: Boolean = true,
) {
    Row(
        modifier = modifier.clickable(enabled = enabled, onClick = onClick).padding(horizontal = 5.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, null, tint = tint.copy(alpha = if (enabled) 1f else .38f), modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(5.dp))
        Text(label, color = tint.copy(alpha = if (enabled) 1f else .38f), fontSize = 10.5.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun VerticalRule() {
    Box(
        modifier = Modifier.padding(vertical = 9.dp).width(1.dp).height(22.dp)
            .background(MaterialTheme.colorScheme.outlineVariant.copy(alpha = .48f)),
    )
}

@Composable
private fun CompactShortcut(
    modifier: Modifier,
    icon: ImageVector,
    title: String,
    subtitle: String,
    onClick: () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = modifier.height(52.dp).clickable(onClick = onClick),
        shape = RoundedCornerShape(InnerRadius),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .14f)),
    ) {
        Row(modifier = Modifier.fillMaxSize().padding(horizontal = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(title, color = tokens.textPrimary, fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                Text(subtitle, color = tokens.textSecondary, fontSize = 8.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
private fun CompactMessageCard(
    icon: ImageVector,
    title: String,
    message: String,
    tint: Color,
    actionLabel: String,
    onClick: () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(InnerRadius),
        color = tint.copy(alpha = .07f),
        border = BorderStroke(1.dp, tint.copy(alpha = .10f)),
    ) {
        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 11.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = tint, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(9.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(title, color = tokens.textPrimary, fontSize = 10.5.sp, fontWeight = FontWeight.SemiBold)
                Text(message, color = tokens.textSecondary, fontSize = 8.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Text(actionLabel, color = tint, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun CompactSectionTitle(title: String) {
    Text(
        text = title,
        modifier = Modifier.padding(start = 2.dp, top = 4.dp, bottom = 0.dp),
        color = LocalLuoShuTokens.current.textPrimary,
        fontSize = 14.sp,
        lineHeight = 18.sp,
        fontWeight = FontWeight.Bold,
    )
}

@Composable
private fun StatusGrid(state: HomeUiState) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(CardRadius),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .13f)),
    ) {
        Column(modifier = Modifier.padding(horizontal = 4.dp, vertical = 3.dp)) {
            StatusPairRow(
                first = StatusData(Icons.Rounded.Security, "Root", if (state.rootGranted) state.rootManager else "未授权", if (state.rootGranted) tokens.success else tokens.danger),
                second = StatusData(Icons.Rounded.Layers, "挂载引擎", state.mountEngine, if (state.mountHealthy) tokens.success else tokens.warning),
            )
            Box(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp).height(1.dp)
                    .background(tokens.outline.copy(alpha = .10f)),
            )
            StatusPairRow(
                first = StatusData(Icons.Rounded.TaskAlt, "当前任务", if (state.taskRunning) "${state.taskProgress}%" else "空闲", if (state.taskRunning) MaterialTheme.colorScheme.primary else tokens.success),
                second = StatusData(Icons.Rounded.RestartAlt, "重启状态", if (state.rebootRequired) "等待重启" else "无需重启", if (state.rebootRequired) tokens.warning else tokens.success),
            )
        }
    }
}

private data class StatusData(
    val icon: ImageVector,
    val title: String,
    val value: String,
    val tint: Color,
)

@Composable
private fun StatusPairRow(first: StatusData, second: StatusData) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        StatusItem(modifier = Modifier.weight(1f), data = first)
        Box(
            modifier = Modifier.width(1.dp).height(26.dp)
                .background(MaterialTheme.colorScheme.outlineVariant.copy(alpha = .40f)),
        )
        StatusItem(modifier = Modifier.weight(1f), data = second)
    }
}

@Composable
private fun StatusItem(modifier: Modifier, data: StatusData) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = modifier.height(42.dp).padding(horizontal = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(data.icon, null, tint = data.tint, modifier = Modifier.size(17.dp))
        Spacer(Modifier.width(7.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(data.title, color = tokens.textSecondary, fontSize = 8.5.sp, lineHeight = 11.sp, maxLines = 1)
            Text(data.value, color = tokens.textPrimary, fontSize = 11.5.sp, lineHeight = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
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

@Composable
private fun NextStepCard(next: HomeNextStep) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(enabled = next.enabled, onClick = next.onClick),
        shape = RoundedCornerShape(CardRadius),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .13f)),
    ) {
        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 11.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(modifier = Modifier.size(32.dp), shape = RoundedCornerShape(10.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = .09f)) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(next.icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                }
            }
            Spacer(Modifier.width(9.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(next.title, color = tokens.textPrimary, fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(next.description, color = tokens.textSecondary, fontSize = 8.5.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Spacer(Modifier.width(7.dp))
            Text(next.actionLabel, color = MaterialTheme.colorScheme.primary, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

private fun nextStepFor(state: HomeUiState, actions: HomeActions): HomeNextStep = when {
    !state.moduleInstalled -> HomeNextStep("连接洛书模块", "安装模块并授予 Root 权限后才能应用全局字体", "检查", Icons.Rounded.Refresh, onClick = actions.refresh)
    state.taskRunning -> HomeNextStep("字体任务正在处理", state.taskMessage.ifBlank { "后台任务会继续运行" }, "任务", Icons.Rounded.Description, onClick = actions.openLogs)
    state.rebootRequired -> HomeNextStep("字体已经准备完成", "完整重启后应用字体并自动验证", "重启", Icons.Rounded.RestartAlt, onClick = actions.reboot)
    state.error.isNotBlank() -> HomeNextStep("发现需要处理的问题", "打开任务中心查看错误与诊断信息", "查看", Icons.Rounded.Warning, onClick = actions.openLogs)
    state.currentFont.contains("系统") -> HomeNextStep("选择一款字体", "从字体库导入、预览并应用单字体", "字体库", Icons.Rounded.FontDownload, onClick = actions.openFontLibrary)
    else -> HomeNextStep("继续调整当前字体", "组合中文、英文与数字字体", "组合", Icons.Rounded.Layers, onClick = actions.openFontStudio)
}

@Composable
private fun SystemWeightCard(weight: HomeWeightUiState, actions: HomeActions) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(CardRadius),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .13f)),
    ) {
        Column(modifier = Modifier.padding(horizontal = 11.dp, vertical = 9.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.Speed, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text("系统字体粗细", color = tokens.textPrimary, fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold)
                    Text("只调整系统渲染参数", color = tokens.textSecondary, fontSize = 8.5.sp)
                }
                Surface(shape = RoundedCornerShape(9.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = .08f)) {
                    Text(
                        text = if (weight.loading) "读取中" else weight.weight.toString(),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 10.5.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
            when {
                weight.loading -> {
                    Spacer(Modifier.height(8.dp))
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth().height(3.dp))
                }
                !weight.supported -> {
                    Spacer(Modifier.height(7.dp))
                    Text(weight.error.ifBlank { "当前系统不支持全局粗细微调" }, color = tokens.danger, fontSize = 9.sp)
                }
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
                            text = weight.error.ifBlank { weight.message },
                            modifier = Modifier.weight(1f),
                            color = if (weight.error.isNotBlank()) tokens.danger else tokens.textSecondary,
                            fontSize = 8.5.sp,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        TextButton(onClick = actions.resetSystemWeight, enabled = !weight.applying) { Text("恢复", fontSize = 10.sp) }
                    }
                }
            }
        }
    }
}
