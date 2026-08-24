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
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens

@Composable
internal fun HomeScreenCompact(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
    trustContent: @Composable () -> Unit,
) {
    val miuix = style == UiStyle.MIUIX
    val dockBottomPadding = maxOf(LocalDockContentPadding.current, 24.dp)
    val tokens = LocalMiuixTokens.current
    val cardColor = if (miuix) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow
    val elevatedColor = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh
    val textPrimary = if (miuix) tokens.textPrimary else MaterialTheme.colorScheme.onSurface
    val textSecondary = if (miuix) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    val shape = RoundedCornerShape(if (miuix) 24.dp else 22.dp)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 14.dp, top = 8.dp, end = 14.dp, bottom = dockBottomPadding),
        verticalArrangement = Arrangement.spacedBy(9.dp),
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
                        fontSize = 30.sp,
                        lineHeight = 34.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        "${if (miuix) "Miuix" else "Material"} · ${state.version}",
                        color = textSecondary,
                        fontSize = 11.sp,
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
                Column(Modifier.padding(16.dp)) {
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
                    Spacer(Modifier.height(12.dp))
                    Text("当前字体", color = textSecondary, fontSize = 11.sp)
                    Text(
                        state.currentFont,
                        color = textPrimary,
                        fontSize = 26.sp,
                        lineHeight = 31.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(12.dp))
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            LuoShuGlyph(
                                imageVector = if (state.taskRunning) Icons.Rounded.Refresh else Icons.Rounded.CheckCircle,
                                contentDescription = null,
                                size = LuoShuIconTokens.StatusGlyph,
                                opticalScale = if (state.taskRunning) 1f else .98f,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(state.taskTitle, color = textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Bold)
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
                        LuoShuGlyph(
                            imageVector = Icons.Rounded.Warning,
                            contentDescription = null,
                            size = LuoShuIconTokens.ToolGlyph,
                            opticalScale = .96f,
                            tint = MaterialTheme.colorScheme.error,
                        )
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
            Card(
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = cardColor),
                elevation = CardDefaults.cardElevation(defaultElevation = if (miuix) 3.dp else 1.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 7.dp, vertical = 9.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CompactStatusCell(
                        modifier = Modifier.weight(1f),
                        icon = Icons.Rounded.Security,
                        title = "Root",
                        value = if (state.rootGranted) state.rootManager else "未授权",
                        healthy = state.rootGranted,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                    Box(Modifier.width(1.dp).height(40.dp).background(textSecondary.copy(alpha = .12f)))
                    CompactStatusCell(
                        modifier = Modifier.weight(1f),
                        icon = Icons.Rounded.Layers,
                        title = "挂载",
                        value = state.mountEngine,
                        healthy = state.mountHealthy,
                        textPrimary = textPrimary,
                        textSecondary = textSecondary,
                    )
                }
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
                    modifier = Modifier.fillMaxWidth().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        modifier = Modifier.size(42.dp),
                        shape = RoundedCornerShape(15.dp),
                        color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            LuoShuGlyph(
                                imageVector = next.icon,
                                contentDescription = null,
                                size = LuoShuIconTokens.StatusGlyph,
                                opticalScale = homeOpticalScale(next.icon),
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(next.title, color = textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Black)
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
                        LuoShuGlyph(
                            imageVector = Icons.Rounded.ChevronRight,
                            contentDescription = null,
                            size = LuoShuIconTokens.TrailingGlyph,
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
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    Text("恢复系统字体", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = actions.reboot,
                    enabled = state.rebootRequired && !state.taskRunning,
                    modifier = Modifier.weight(1f).height(48.dp),
                    shape = RoundedCornerShape(16.dp),
                ) {
                    LuoShuGlyph(
                        imageVector = Icons.Rounded.RestartAlt,
                        contentDescription = null,
                        size = LuoShuIconTokens.SectionGlyph,
                    )
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


private fun homeOpticalScale(icon: ImageVector): Float = when (icon) {
    Icons.Rounded.Security -> .95f
    Icons.Rounded.Layers -> .96f
    Icons.Rounded.Description -> .96f
    Icons.Rounded.FontDownload -> .98f
    Icons.Rounded.Warning -> .96f
    Icons.Rounded.RestartAlt -> .96f
    else -> 1f
}

@Composable
private fun HeaderAction(
    icon: ImageVector,
    description: String,
    containerColor: Color,
    loading: Boolean = false,
    onClick: () -> Unit,
) {
    LuoShuHeaderAction(
        icon = icon,
        contentDescription = description,
        onClick = onClick,
        containerColor = containerColor,
        loading = loading,
        opticalScale = if (icon == Icons.Rounded.Settings) .94f else 1f,
    )
}

@Composable
private fun CompactStatusCell(
    modifier: Modifier,
    icon: ImageVector,
    title: String,
    value: String,
    healthy: Boolean,
    textPrimary: Color,
    textSecondary: Color,
) {
    val accent = if (healthy) Color(0xFF21966C) else MaterialTheme.colorScheme.error
    Row(
        modifier = modifier.padding(horizontal = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(
            modifier = Modifier.size(36.dp),
            shape = RoundedCornerShape(13.dp),
            color = accent.copy(alpha = .09f),
        ) {
            Box(contentAlignment = Alignment.Center) {
                LuoShuGlyph(
                    imageVector = icon,
                    contentDescription = null,
                    size = LuoShuIconTokens.SectionGlyph,
                    opticalScale = homeOpticalScale(icon),
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                value,
                color = textPrimary,
                fontSize = 12.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "$title · ${if (healthy) "正常" else "需检查"}",
                color = if (healthy) textSecondary else accent,
                fontSize = 9.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
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
                        LuoShuGlyph(
                            imageVector = Icons.Rounded.Speed,
                            contentDescription = null,
                            size = LuoShuIconTokens.StatusGlyph,
                            opticalScale = .96f,
                            tint = MaterialTheme.colorScheme.primary,
                        )
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
