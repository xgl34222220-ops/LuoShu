package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
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
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.Slider
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun HomeScreenMiuix(
    state: HomeUiState,
    actions: HomeActions,
    trustContent: @Composable () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background),
        contentPadding = PaddingValues(start = 16.dp, top = 18.dp, end = 16.dp, bottom = 112.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Column(modifier = Modifier.padding(horizontal = 4.dp, vertical = 8.dp)) {
                Text(
                    text = "洛书",
                    fontSize = 34.sp,
                    fontWeight = FontWeight.Bold,
                    color = colors.onBackground,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = "无 Hook 全局字体引擎 · ${state.version}",
                    fontSize = 14.sp,
                    color = colors.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }

        item {
            MiuixHomeCard(
                title = state.currentFont,
                summary = engineSummary(state),
                icon = Icons.Rounded.FontDownload,
                onClick = actions.openFontLibrary,
            )
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "刷新状态",
                    summary = if (state.loading) "正在重新读取模块与字体状态" else "重新检查字体、挂载和任务状态",
                    startAction = { MiuixHomeIcon(Icons.Rounded.Refresh) },
                    enabled = !state.loading,
                    onClick = actions.refresh,
                )
                BasicComponent(
                    title = "恢复系统字体",
                    summary = "撤销当前字体覆盖并恢复 ROM 原始映射",
                    startAction = { MiuixHomeIcon(Icons.Rounded.Restore) },
                    enabled = !state.taskRunning,
                    onClick = actions.restoreDefault,
                )
                BasicComponent(
                    title = if (state.rebootRequired) "完整重启" else "任务中心",
                    summary = if (state.rebootRequired) "当前字体已准备完成，重启后生效" else taskSummary(state),
                    startAction = {
                        MiuixHomeIcon(if (state.rebootRequired) Icons.Rounded.RestartAlt else Icons.Rounded.Description)
                    },
                    onClick = if (state.rebootRequired) actions.reboot else actions.openLogs,
                )
            }
        }

        item { trustContent() }

        if (state.error.isNotBlank()) {
            item {
                MiuixHomeCard(
                    title = "字体引擎需要处理",
                    summary = state.error,
                    icon = Icons.Rounded.Warning,
                    onClick = actions.openLogs,
                )
            }
        }

        item { MiuixSectionTitle("设备状态") }
        item {
            MiuixHomeCard(
                title = "Root",
                summary = if (state.rootGranted) "已由 ${state.rootManager} 授予字体事务权限" else "尚未获得 Root 权限",
                icon = Icons.Rounded.Security,
                onClick = actions.refresh,
            )
        }
        item {
            MiuixHomeCard(
                title = "挂载引擎",
                summary = state.mountEngine,
                icon = Icons.Rounded.Layers,
                onClick = actions.openLogs,
            )
        }
        item {
            MiuixHomeCard(
                title = "当前任务",
                summary = taskSummary(state),
                icon = Icons.Rounded.TaskAlt,
                onClick = actions.openLogs,
            )
        }
        item {
            MiuixHomeCard(
                title = "重启状态",
                summary = if (state.rebootRequired) "等待完整重启" else "当前操作无需重启",
                icon = Icons.Rounded.RestartAlt,
                onClick = if (state.rebootRequired) actions.reboot else actions.openLogs,
            )
        }

        item { MiuixSectionTitle("下一步") }
        item {
            val next = miuixNextStep(state, actions)
            MiuixHomeCard(
                title = next.title,
                summary = next.summary,
                icon = next.icon,
                enabled = next.enabled,
                onClick = next.onClick,
            )
        }

        item { MiuixSectionTitle("全局粗细") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "系统字体粗细",
                    summary = when {
                        state.systemWeight.loading -> "正在读取系统渲染参数"
                        !state.systemWeight.supported -> state.systemWeight.error.ifBlank { "当前系统不支持粗细微调" }
                        else -> "当前 ${state.systemWeight.weight} · 仅调整系统渲染参数"
                    },
                    startAction = { MiuixHomeIcon(Icons.Rounded.Speed) },
                )
                if (state.systemWeight.supported && !state.systemWeight.loading) {
                    val range = (state.systemWeight.max - state.systemWeight.min).coerceAtLeast(1)
                    val normalized = ((state.systemWeight.weight - state.systemWeight.min).toFloat() / range.toFloat())
                        .coerceIn(0f, 1f)
                    Slider(
                        value = normalized,
                        onValueChange = { value ->
                            val raw = state.systemWeight.min + (range * value).toInt()
                            val step = state.systemWeight.step.coerceAtLeast(1)
                            val snapped = state.systemWeight.min + ((raw - state.systemWeight.min) / step) * step
                            actions.previewSystemWeight(snapped.toFloat())
                        },
                        enabled = !state.systemWeight.applying,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 4.dp),
                    )
                }
                BasicComponent(
                    title = "恢复原始粗细",
                    summary = "恢复系统默认字体渲染参数",
                    enabled = !state.systemWeight.applying,
                    onClick = actions.resetSystemWeight,
                )
                BasicComponent(
                    title = "打开字体组合",
                    summary = "分别选择中文、英文和数字字体",
                    onClick = actions.openFontStudio,
                )
            }
        }
    }
}

@Composable
private fun MiuixHomeCard(
    title: String,
    summary: String,
    icon: ImageVector,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = title,
            summary = summary,
            startAction = { MiuixHomeIcon(icon) },
            enabled = enabled,
            onClick = onClick,
        )
    }
}

@Composable
private fun MiuixHomeIcon(icon: ImageVector) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = MiuixTheme.colorScheme.primary,
        modifier = Modifier.padding(end = 16.dp).size(24.dp),
    )
}

@Composable
private fun MiuixSectionTitle(title: String) {
    Text(
        text = title,
        color = MiuixTheme.colorScheme.onBackground,
        fontSize = 20.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(start = 4.dp, top = 14.dp, bottom = 2.dp),
    )
}

private data class MiuixNextStep(
    val title: String,
    val summary: String,
    val icon: ImageVector,
    val enabled: Boolean = true,
    val onClick: () -> Unit,
)

private fun miuixNextStep(state: HomeUiState, actions: HomeActions): MiuixNextStep = when {
    !state.moduleInstalled -> MiuixNextStep(
        title = "连接洛书模块",
        summary = "安装模块并授予 Root 权限后才能应用全局字体",
        icon = Icons.Rounded.Refresh,
        onClick = actions.refresh,
    )
    state.taskRunning -> MiuixNextStep(
        title = "字体任务正在处理",
        summary = state.taskMessage.ifBlank { "可以离开 App，后台任务会继续运行" },
        icon = Icons.Rounded.Description,
        onClick = actions.openLogs,
    )
    state.rebootRequired -> MiuixNextStep(
        title = "字体已经准备完成",
        summary = "执行一次完整重启后应用全局字体并自动验证",
        icon = Icons.Rounded.RestartAlt,
        onClick = actions.reboot,
    )
    state.error.isNotBlank() -> MiuixNextStep(
        title = "发现需要处理的问题",
        summary = "打开任务中心查看错误原因与诊断信息",
        icon = Icons.Rounded.Warning,
        onClick = actions.openLogs,
    )
    state.currentFont.contains("系统") -> MiuixNextStep(
        title = "选择一款字体",
        summary = "从字体库导入、预览并应用单字体",
        icon = Icons.Rounded.FontDownload,
        onClick = actions.openFontLibrary,
    )
    else -> MiuixNextStep(
        title = "继续调整当前字体",
        summary = "组合中文、英文与数字字体，或调整真实设计轴",
        icon = Icons.Rounded.Layers,
        onClick = actions.openFontStudio,
    )
}

private fun engineSummary(state: HomeUiState): String = when {
    state.error.isNotBlank() -> state.error
    state.taskRunning -> state.taskMessage.ifBlank { "任务执行中 · ${state.taskProgress}%" }
    state.rebootRequired -> "字体负载已准备完成，等待完整重启"
    state.moduleInstalled && state.rootGranted && state.mountHealthy -> "字体引擎运行正常"
    else -> "正在检查模块、Root 与挂载环境"
}

private fun taskSummary(state: HomeUiState): String = when {
    state.taskRunning -> state.taskMessage.ifBlank { "${state.taskTitle} · ${state.taskProgress}%" }
    state.taskMessage.isNotBlank() -> state.taskMessage
    state.taskTitle.isNotBlank() -> state.taskTitle
    else -> "暂无后台任务"
}
