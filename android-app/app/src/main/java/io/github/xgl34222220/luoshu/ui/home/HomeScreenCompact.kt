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
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Restore
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.TaskAlt
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
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
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.design.LuoShuDivider
import io.github.xgl34222220.luoshu.ui.design.LuoShuGroupCard
import io.github.xgl34222220.luoshu.ui.design.LuoShuIconButton
import io.github.xgl34222220.luoshu.ui.design.LuoShuIconTile
import io.github.xgl34222220.luoshu.ui.design.LuoShuMetricTile
import io.github.xgl34222220.luoshu.ui.design.LuoShuPageHeader
import io.github.xgl34222220.luoshu.ui.design.LuoShuSectionTitle
import io.github.xgl34222220.luoshu.ui.design.LuoShuSettingRow
import io.github.xgl34222220.luoshu.ui.theme.LocalLuoShuTokens

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
            start = tokens.pagePadding,
            top = 0.dp,
            end = tokens.pagePadding,
            bottom = 88.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(tokens.compactGap),
    ) {
        item {
            LuoShuPageHeader(
                title = "洛书",
                subtitle = "无 Hook 全局字体引擎 · ${state.version}",
                centered = true,
                leading = {
                    LuoShuIconButton(
                        icon = Icons.Rounded.Description,
                        contentDescription = "任务中心",
                        onClick = actions.openLogs,
                    )
                },
                actions = {
                    LuoShuIconButton(
                        icon = Icons.Rounded.Refresh,
                        contentDescription = "刷新",
                        onClick = actions.refresh,
                        enabled = !state.loading,
                        content = if (state.loading) {
                            { CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp) }
                        } else null,
                    )
                    LuoShuIconButton(
                        icon = Icons.Rounded.Settings,
                        contentDescription = "设置",
                        onClick = actions.openSettings,
                    )
                },
            )
        }

        item { EngineStatusCard(state = state, actions = actions) }
        item { trustContent() }

        if (state.error.isNotBlank()) {
            item {
                LuoShuGroupCard {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        LuoShuIconTile(
                            icon = Icons.Rounded.Warning,
                            tint = tokens.danger,
                            containerColor = tokens.danger.copy(alpha = .09f),
                        )
                        Spacer(Modifier.width(10.dp))
                        Column(Modifier.weight(1f)) {
                            Text("字体引擎需要处理", color = tokens.textPrimary, style = MaterialTheme.typography.titleSmall)
                            Text(
                                state.error,
                                color = tokens.textSecondary,
                                style = MaterialTheme.typography.bodySmall,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        TextButton(onClick = actions.openLogs) { Text("查看") }
                    }
                }
            }
        }

        item { LuoShuSectionTitle("设备状态") }
        item {
            LuoShuGroupCard {
                Column {
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Security,
                        title = "Root",
                        description = if (state.rootGranted) "已获得字体事务权限" else "尚未获得 Root 授权",
                        value = if (state.rootGranted) state.rootManager else "未授权",
                    )
                    LuoShuDivider(Modifier.padding(start = 56.dp))
                    LuoShuSettingRow(
                        icon = Icons.Rounded.Layers,
                        title = "挂载引擎",
                        description = if (state.mountHealthy) "当前挂载链工作正常" else "挂载状态需要检查",
                        value = state.mountEngine,
                    )
                    LuoShuDivider(Modifier.padding(start = 56.dp))
                    LuoShuSettingRow(
                        icon = Icons.Rounded.TaskAlt,
                        title = "当前任务",
                        description = state.taskMessage.ifBlank { state.taskTitle },
                        value = if (state.taskRunning) "${state.taskProgress}%" else "空闲",
                        showChevron = true,
                        onClick = actions.openLogs,
                    )
                    LuoShuDivider(Modifier.padding(start = 56.dp))
                    LuoShuSettingRow(
                        icon = Icons.Rounded.RestartAlt,
                        title = "重启状态",
                        description = if (state.rebootRequired) "字体负载已准备，等待完整重启" else "本次操作无需重启",
                        value = if (state.rebootRequired) "等待重启" else "无需重启",
                        onClick = if (state.rebootRequired) actions.reboot else null,
                    )
                }
            }
        }

        item { LuoShuSectionTitle("下一步") }
        item { NextStepCard(next = nextStepFor(state, actions)) }

        item { LuoShuSectionTitle("全局粗细") }
        item { SystemWeightCard(weight = state.systemWeight, actions = actions) }
    }
}

@Composable
private fun EngineStatusCard(state: HomeUiState, actions: HomeActions) {
    val tokens = LocalLuoShuTokens.current
    val healthy = state.moduleInstalled && state.rootGranted && state.mountHealthy
    val statusColor = when {
        state.error.isNotBlank() -> tokens.danger
        state.rebootRequired -> tokens.warning
        healthy -> tokens.success
        else -> MaterialTheme.colorScheme.primary
    }
    val statusLabel = when {
        state.taskRunning -> "任务执行中"
        state.rebootRequired -> "等待完整重启"
        healthy -> "字体引擎运行正常"
        else -> "正在检查运行环境"
    }

    LuoShuGroupCard(elevated = true) {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    shape = RoundedCornerShape(999.dp),
                    color = statusColor.copy(alpha = .10f),
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(7.dp).background(statusColor, CircleShape))
                        Spacer(Modifier.width(6.dp))
                        Text(statusLabel, color = statusColor, style = MaterialTheme.typography.labelMedium)
                    }
                }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = actions.openLogs) { Text("详情") }
            }
            Spacer(Modifier.height(10.dp))
            Text("当前字体", color = tokens.textSecondary, style = MaterialTheme.typography.bodySmall)
            Text(
                text = state.currentFont,
                color = tokens.textPrimary,
                style = MaterialTheme.typography.headlineSmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = state.taskMessage.ifBlank { state.taskTitle },
                color = tokens.textSecondary,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            if (state.taskRunning) {
                Spacer(Modifier.height(10.dp))
                LinearProgressIndicator(
                    progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                    modifier = Modifier.fillMaxWidth().height(4.dp),
                    color = MaterialTheme.colorScheme.primary,
                    trackColor = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                )
            }
            Spacer(Modifier.height(12.dp))
            LuoShuDivider()
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusAction(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.FontDownload,
                    label = "字体库",
                    onClick = actions.openFontLibrary,
                )
                StatusAction(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Restore,
                    label = "恢复",
                    enabled = !state.taskRunning,
                    tint = tokens.danger,
                    onClick = actions.restoreDefault,
                )
                StatusAction(
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
private fun StatusAction(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    tint: Color = MaterialTheme.colorScheme.primary,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = modifier
            .height(44.dp)
            .clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(14.dp),
        color = tokens.surfaceAlt.copy(alpha = if (enabled) 1f else .48f),
        border = androidx.compose.foundation.BorderStroke(1.dp, tokens.outline.copy(alpha = .22f)),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, contentDescription = null, tint = tint.copy(alpha = if (enabled) 1f else .45f), modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(label, color = tokens.textPrimary.copy(alpha = if (enabled) 1f else .45f), style = MaterialTheme.typography.labelLarge)
        }
    }
}

private data class HomeNextStep(
    val title: String,
    val description: String,
    val actionLabel: String,
    val icon: ImageVector,
    val onClick: () -> Unit,
    val enabled: Boolean = true,
)

@Composable
private fun NextStepCard(next: HomeNextStep) {
    val tokens = LocalLuoShuTokens.current
    LuoShuGroupCard(
        modifier = Modifier.fillMaxWidth().clickable(enabled = next.enabled, onClick = next.onClick),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LuoShuIconTile(icon = next.icon)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(next.title, color = tokens.textPrimary, style = MaterialTheme.typography.titleMedium)
                Text(
                    next.description,
                    color = tokens.textSecondary,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.width(8.dp))
            Text(
                next.actionLabel,
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.labelMedium,
                textAlign = TextAlign.End,
            )
        }
    }
}

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
private fun SystemWeightCard(
    weight: HomeWeightUiState,
    actions: HomeActions,
) {
    val tokens = LocalLuoShuTokens.current
    LuoShuGroupCard {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                LuoShuIconTile(icon = Icons.Rounded.Speed)
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("系统字体粗细", color = tokens.textPrimary, style = MaterialTheme.typography.titleMedium)
                    Text("只调整系统渲染参数，不修改字体文件", color = tokens.textSecondary, style = MaterialTheme.typography.bodySmall)
                }
                Surface(
                    shape = RoundedCornerShape(tokens.smallRadius),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                ) {
                    Text(
                        if (weight.loading) "读取中" else weight.weight.toString(),
                        modifier = Modifier.padding(horizontal = 11.dp, vertical = 7.dp),
                        color = MaterialTheme.colorScheme.primary,
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
            }
            Spacer(Modifier.height(10.dp))
            when {
                weight.loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
                !weight.supported -> Text(
                    weight.error.ifBlank { "当前系统不支持全局粗细微调" },
                    color = tokens.danger,
                    style = MaterialTheme.typography.bodySmall,
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
                            color = if (weight.error.isNotBlank()) tokens.danger else tokens.textSecondary,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                        )
                        TextButton(onClick = actions.resetSystemWeight, enabled = !weight.applying) {
                            Text("恢复原始")
                        }
                    }
                }
            }
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = actions.restoreDefault,
                    enabled = !weight.applying,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(tokens.fieldRadius),
                ) {
                    Text("恢复系统字体")
                }
                Button(
                    onClick = actions.openFontStudio,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(tokens.fieldRadius),
                ) {
                    Text("打开字体组合")
                }
            }
        }
    }
}
