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
import androidx.compose.foundation.layout.widthIn
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
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalLuoShuTokens

private val PagePadding = 12.dp
private val GroupRadius = 22.dp
private val RowHeight = 58.dp

@Composable
@Suppress("UNUSED_PARAMETER")
internal fun HomeScreenVideoExact(
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
            top = 10.dp,
            end = PagePadding,
            bottom = 104.dp,
        ),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item { HomeHeader(state = state, actions = actions) }
        item { EngineSummary(state = state, actions = actions) }
        item { trustContent() }

        if (state.error.isNotBlank()) {
            item {
                MessageRow(
                    icon = Icons.Rounded.Warning,
                    title = "字体引擎需要处理",
                    message = state.error,
                    tint = tokens.danger,
                    action = "查看",
                    onClick = actions.openLogs,
                )
            }
        }

        item { SectionTitle("设备状态") }
        item { DeviceStatusGroup(state = state, actions = actions) }

        item { SectionTitle("下一步") }
        item { NextStepGroup(next = nextStepFor(state, actions)) }

        item { SectionTitle("全局粗细") }
        item { WeightGroup(weight = state.systemWeight, actions = actions) }
    }
}

@Composable
private fun HomeHeader(state: HomeUiState, actions: HomeActions) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 4.dp, end = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                text = "洛书",
                color = tokens.textPrimary,
                fontSize = 28.sp,
                lineHeight = 34.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
            Text(
                text = "无 Hook 全局字体引擎 · ${state.version}",
                color = tokens.textSecondary,
                fontSize = 13.sp,
                lineHeight = 18.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        HeaderAction(
            icon = Icons.Rounded.Refresh,
            description = "刷新",
            enabled = !state.loading,
            onClick = actions.refresh,
            loading = state.loading,
        )
        Spacer(Modifier.width(8.dp))
        HeaderAction(
            icon = Icons.Rounded.Settings,
            description = "设置",
            onClick = actions.openSettings,
        )
    }
}

@Composable
private fun HeaderAction(
    icon: ImageVector,
    description: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    loading: Boolean = false,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = Modifier.size(44.dp).clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(15.dp),
        color = MaterialTheme.colorScheme.surface.copy(alpha = .94f),
        tonalElevation = 0.dp,
        shadowElevation = 0.dp,
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp),
                    strokeWidth = 2.dp,
                    color = MaterialTheme.colorScheme.primary,
                )
            } else {
                Icon(
                    imageVector = icon,
                    contentDescription = description,
                    tint = tokens.textPrimary.copy(alpha = if (enabled) 1f else .38f),
                    modifier = Modifier.size(22.dp),
                )
            }
        }
    }
}

@Composable
private fun EngineSummary(state: HomeUiState, actions: HomeActions) {
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

    VideoGroup {
        Column(Modifier.fillMaxWidth()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 16.dp, top = 15.dp, end = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(7.dp).background(statusColor, CircleShape))
                Spacer(Modifier.width(8.dp))
                Text(
                    text = statusText,
                    color = statusColor,
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                Surface(
                    modifier = Modifier.size(40.dp),
                    shape = CircleShape,
                    color = statusColor.copy(alpha = .10f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        if (state.taskRunning) {
                            CircularProgressIndicator(
                                progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                                modifier = Modifier.size(25.dp),
                                color = statusColor,
                                trackColor = statusColor.copy(alpha = .13f),
                                strokeWidth = 3.dp,
                            )
                        } else {
                            Icon(
                                imageVector = if (state.error.isBlank()) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                                contentDescription = null,
                                tint = statusColor,
                                modifier = Modifier.size(24.dp),
                            )
                        }
                    }
                }
            }

            Column(Modifier.padding(start = 16.dp, top = 4.dp, end = 16.dp, bottom = 13.dp)) {
                Text(
                    text = state.currentFont,
                    color = tokens.textPrimary,
                    fontSize = 26.sp,
                    lineHeight = 32.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = state.taskMessage.ifBlank { state.taskTitle },
                    color = tokens.textSecondary,
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
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
            }

            SoftDivider()
            Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 3.dp)) {
                PlainAction(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Refresh,
                    label = "刷新",
                    onClick = actions.refresh,
                    enabled = !state.loading,
                )
                VerticalSoftDivider()
                PlainAction(
                    modifier = Modifier.weight(1f),
                    icon = Icons.Rounded.Restore,
                    label = "恢复",
                    tint = tokens.danger,
                    onClick = actions.restoreDefault,
                    enabled = !state.taskRunning,
                )
                VerticalSoftDivider()
                PlainAction(
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
private fun PlainAction(
    modifier: Modifier,
    icon: ImageVector,
    label: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    tint: Color = MaterialTheme.colorScheme.primary,
) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = modifier.height(46.dp).clickable(enabled = enabled, onClick = onClick),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = tint.copy(alpha = if (enabled) 1f else .38f),
            modifier = Modifier.size(19.dp),
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text = label,
            color = tokens.textPrimary.copy(alpha = if (enabled) .88f else .38f),
            fontSize = 13.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
private fun DeviceStatusGroup(state: HomeUiState, actions: HomeActions) {
    val tokens = LocalLuoShuTokens.current
    VideoGroup {
        Column {
            StatusRow(
                icon = Icons.Rounded.Security,
                title = "Root 权限",
                subtitle = if (state.rootGranted) "字体事务权限已获得" else "需要授予 Root 权限",
                value = if (state.rootGranted) state.rootManager else "未授权",
                tint = if (state.rootGranted) tokens.success else tokens.danger,
            )
            SoftDivider(indented = true)
            StatusRow(
                icon = Icons.Rounded.Layers,
                title = "挂载引擎",
                subtitle = if (state.mountHealthy) "当前挂载链工作正常" else "挂载链需要检查",
                value = state.mountEngine,
                tint = if (state.mountHealthy) tokens.success else tokens.warning,
            )
            SoftDivider(indented = true)
            StatusRow(
                icon = Icons.Rounded.TaskAlt,
                title = "当前任务",
                subtitle = state.taskMessage.ifBlank { "暂无后台字体任务" },
                value = if (state.taskRunning) "${state.taskProgress}%" else "空闲",
                tint = if (state.taskRunning) MaterialTheme.colorScheme.primary else tokens.success,
                onClick = actions.openLogs,
            )
            SoftDivider(indented = true)
            StatusRow(
                icon = Icons.Rounded.RestartAlt,
                title = "重启状态",
                subtitle = if (state.rebootRequired) "重启后应用并验证字体" else "本次操作无需重启",
                value = if (state.rebootRequired) "等待重启" else "无需重启",
                tint = if (state.rebootRequired) tokens.warning else tokens.success,
                onClick = if (state.rebootRequired) actions.reboot else null,
            )
        }
    }
}

@Composable
private fun StatusRow(
    icon: ImageVector,
    title: String,
    subtitle: String,
    value: String,
    tint: Color,
    onClick: (() -> Unit)? = null,
) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = RowHeight)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(horizontal = 14.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(
            modifier = Modifier.size(36.dp),
            shape = RoundedCornerShape(12.dp),
            color = tint.copy(alpha = .09f),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
            }
        }
        Spacer(Modifier.width(11.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                color = tokens.textPrimary,
                fontSize = 15.sp,
                lineHeight = 19.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
            )
            Text(
                text = subtitle,
                color = tokens.textSecondary,
                fontSize = 11.sp,
                lineHeight = 16.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Spacer(Modifier.width(10.dp))
        Text(
            text = value,
            color = MaterialTheme.colorScheme.primary,
            fontSize = 12.sp,
            lineHeight = 17.sp,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.End,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 130.dp),
        )
    }
}

private data class NextStep(
    val title: String,
    val description: String,
    val actionLabel: String,
    val icon: ImageVector,
    val tint: Color? = null,
    val enabled: Boolean = true,
    val onClick: () -> Unit,
)

@Composable
private fun NextStepGroup(next: NextStep) {
    val tokens = LocalLuoShuTokens.current
    val tint = next.tint ?: MaterialTheme.colorScheme.primary
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(enabled = next.enabled, onClick = next.onClick),
        shape = RoundedCornerShape(GroupRadius),
        color = MaterialTheme.colorScheme.primary.copy(alpha = .075f),
        tonalElevation = 0.dp,
        shadowElevation = 0.dp,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(40.dp),
                shape = RoundedCornerShape(13.dp),
                color = tint.copy(alpha = .10f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(next.icon, contentDescription = null, tint = tint, modifier = Modifier.size(22.dp))
                }
            }
            Spacer(Modifier.width(11.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = next.title,
                    color = tokens.textPrimary,
                    fontSize = 15.sp,
                    lineHeight = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = next.description,
                    color = tokens.textSecondary,
                    fontSize = 11.sp,
                    lineHeight = 16.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.width(8.dp))
            Text(
                text = next.actionLabel,
                color = tint,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.End,
            )
        }
    }
}

@Composable
private fun WeightGroup(weight: HomeWeightUiState, actions: HomeActions) {
    val tokens = LocalLuoShuTokens.current
    VideoGroup {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(36.dp),
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .09f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.Rounded.Speed,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
                Spacer(Modifier.width(11.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        text = "系统字体粗细",
                        color = tokens.textPrimary,
                        fontSize = 15.sp,
                        lineHeight = 20.sp,
                        fontWeight = FontWeight.Medium,
                    )
                    Text(
                        text = "仅调整系统渲染参数",
                        color = tokens.textSecondary,
                        fontSize = 11.sp,
                        lineHeight = 16.sp,
                    )
                }
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                ) {
                    Text(
                        text = weight.weight.toString(),
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                    )
                }
            }

            Spacer(Modifier.height(7.dp))
            when {
                weight.loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
                !weight.supported -> Text(
                    text = weight.error.ifBlank { "当前系统不支持全局粗细微调" },
                    color = tokens.danger,
                    fontSize = 11.sp,
                    lineHeight = 16.sp,
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
                            text = weight.error.ifBlank { weight.message },
                            modifier = Modifier.weight(1f),
                            color = if (weight.error.isNotBlank()) tokens.danger else tokens.textSecondary,
                            fontSize = 11.sp,
                            lineHeight = 16.sp,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        TextButton(onClick = actions.resetSystemWeight, enabled = !weight.applying) {
                            Text("恢复原始", fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MessageRow(
    icon: ImageVector,
    title: String,
    message: String,
    tint: Color,
    action: String,
    onClick: () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = tint.copy(alpha = .075f),
        tonalElevation = 0.dp,
        shadowElevation = 0.dp,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(title, color = tokens.textPrimary, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                Text(
                    message,
                    color = tokens.textSecondary,
                    fontSize = 11.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(action, color = tint, fontSize = 12.sp, fontWeight = FontWeight.Medium)
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    val tokens = LocalLuoShuTokens.current
    Text(
        text = text,
        color = tokens.textPrimary,
        fontSize = 18.sp,
        lineHeight = 23.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(start = 4.dp, top = 7.dp, bottom = 1.dp),
    )
}

@Composable
private fun VideoGroup(content: @Composable () -> Unit) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(GroupRadius),
        color = MaterialTheme.colorScheme.surface.copy(alpha = .96f),
        tonalElevation = 0.dp,
        shadowElevation = 0.dp,
        content = content,
    )
}

@Composable
private fun SoftDivider(indented: Boolean = false) {
    val tokens = LocalLuoShuTokens.current
    Box(
        Modifier
            .fillMaxWidth()
            .padding(start = if (indented) 61.dp else 0.dp, end = 14.dp)
            .height(1.dp)
            .background(tokens.outline.copy(alpha = .12f)),
    )
}

@Composable
private fun VerticalSoftDivider() {
    val tokens = LocalLuoShuTokens.current
    Box(Modifier.width(1.dp).height(22.dp).background(tokens.outline.copy(alpha = .14f)))
}

private fun nextStepFor(state: HomeUiState, actions: HomeActions): NextStep = when {
    !state.moduleInstalled -> NextStep(
        title = "连接洛书模块",
        description = "安装模块并授予 Root 权限后才能应用全局字体",
        actionLabel = "检查",
        icon = Icons.Rounded.Refresh,
        onClick = actions.refresh,
    )
    state.taskRunning -> NextStep(
        title = "字体任务正在处理",
        description = state.taskMessage.ifBlank { "后台任务会继续运行" },
        actionLabel = "任务",
        icon = Icons.Rounded.Description,
        onClick = actions.openLogs,
    )
    state.rebootRequired -> NextStep(
        title = "字体已经准备完成",
        description = "完整重启后应用并自动验证字体",
        actionLabel = "重启",
        icon = Icons.Rounded.RestartAlt,
        onClick = actions.reboot,
    )
    state.error.isNotBlank() -> NextStep(
        title = "发现需要处理的问题",
        description = "打开任务中心查看原因和诊断信息",
        actionLabel = "查看",
        icon = Icons.Rounded.Warning,
        onClick = actions.openLogs,
    )
    state.currentFont.contains("系统") -> NextStep(
        title = "选择一款字体",
        description = "从字体库导入、预览并应用字体",
        actionLabel = "字体库",
        icon = Icons.Rounded.FontDownload,
        onClick = actions.openFontLibrary,
    )
    else -> NextStep(
        title = "继续调整当前字体",
        description = "组合中文、英文和数字字体",
        actionLabel = "组合",
        icon = Icons.Rounded.Layers,
        onClick = actions.openFontStudio,
    )
}
