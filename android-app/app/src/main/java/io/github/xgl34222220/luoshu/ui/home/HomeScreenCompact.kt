package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Layers
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material.icons.rounded.RestartAlt
import androidx.compose.material.icons.rounded.Security
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLayoutTokens
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLoadingSkeleton
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSectionHeading
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTopBar
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
internal fun HomeScreenCompact(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
    trustContent: @Composable () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val scheme = MaterialTheme.colorScheme
    val cardColor = tokens.cardBackground
    val textPrimary = tokens.textPrimary
    val textSecondary = tokens.textSecondary
    val shape = RoundedCornerShape(24.dp)
    var deviceDetailsExpanded by rememberSaveable { mutableStateOf(false) }
    val canChange = state.moduleInstalled && state.rootGranted && !state.taskRunning
    val next = nextStepFor(state, actions)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = LuoShuLayoutTokens.PageHorizontal,
            end = LuoShuLayoutTokens.PageHorizontal,
            bottom = maxOf(LocalDockContentPadding.current, LuoShuLayoutTokens.FloatingDockSafeBottom),
        ),
        verticalArrangement = Arrangement.spacedBy(LuoShuLayoutTokens.ItemGap),
    ) {
        item(key = "header") {
            LuoShuTopBar(title = "洛书") {
                LuoShuHeaderAction(
                    icon = Icons.Rounded.Description,
                    contentDescription = "任务中心",
                    onClick = actions.openLogs,
                    containerColor = cardColor,
                )
                LuoShuHeaderAction(
                    icon = Icons.Rounded.Refresh,
                    contentDescription = "刷新",
                    onClick = actions.refresh,
                    containerColor = cardColor,
                    loading = state.loading,
                )
            }
        }
        item(key = "current-font") {
            val dark = scheme.background.luminance() < .5f
            Surface(
                shape = RoundedCornerShape(28.dp),
                color = cardColor,
                shadowElevation = 2.dp,
                border = BorderStroke(
                    0.5.dp,
                    if (dark) Color.Transparent else LuoShuLayoutTokens.LightCardOutline,
                ),
            ) {
                Column(
                    Modifier.fillMaxWidth()
                        .background(Brush.linearGradient(listOf(scheme.primaryContainer.copy(alpha = .46f), cardColor)))
                        .padding(22.dp),
                    verticalArrangement = Arrangement.spacedBy(18.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(shape = CircleShape, color = cardColor.copy(alpha = .72f)) {
                            Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                                Box(Modifier.size(6.dp).background(if (state.moduleInstalled && state.rootGranted) tokens.success else tokens.warning, CircleShape))
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    when {
                                        state.loading -> "正在连接"
                                        !state.moduleInstalled -> "等待模块"
                                        !state.rootGranted -> "需要授权"
                                        state.taskRunning -> "正在处理"
                                        state.rebootRequired -> "等待重启"
                                        else -> "模块已连接"
                                    },
                                    color = textPrimary,
                                    style = MaterialTheme.typography.labelMedium,
                                )
                            }
                        }
                        Spacer(Modifier.weight(1f))
                        Text(state.version, color = textSecondary, style = MaterialTheme.typography.labelMedium)
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("当前字体", color = textSecondary, style = MaterialTheme.typography.bodySmall)
                        Text(state.currentFont, color = textPrimary, fontSize = 24.sp, lineHeight = 32.sp,
                            fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Text("字里行间，自有风格。", color = textPrimary, fontSize = 25.sp, lineHeight = 36.sp,
                            fontWeight = FontWeight.Medium)
                        Text("Aa Bb  ·  0123456789", color = scheme.primary, fontSize = 19.sp,
                            lineHeight = 28.sp, letterSpacing = .5.sp)
                    }
                    Button(
                        onClick = next.onClick,
                        enabled = next.enabled,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
                        shape = RoundedCornerShape(18.dp),
                    ) {
                        LuoShuGlyph(next.icon, null, LuoShuIconTokens.ToolGlyph)
                        Spacer(Modifier.width(8.dp))
                        Text(next.actionLabel, style = MaterialTheme.typography.labelLarge)
                    }
                }
            }
        }
        if (state.taskRunning || state.rebootRequired || state.error.isNotBlank()) {
            item(key = "task-status") {
                val failed = state.error.isNotBlank() && !state.taskRunning
                Surface(
                    color = if (failed) scheme.errorContainer else cardColor,
                    shape = shape,
                    modifier = Modifier.fillMaxWidth().clip(shape).clickable(onClick = actions.openLogs),
                ) {
                    Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            LuoShuGlyph(
                                if (failed) Icons.Rounded.Warning else if (state.rebootRequired) Icons.Rounded.RestartAlt else Icons.Rounded.Refresh,
                                null, LuoShuIconTokens.StatusGlyph,
                                tint = if (failed) scheme.error else scheme.primary,
                            )
                            Text(if (state.rebootRequired && !state.taskRunning) "重启后生效" else state.taskTitle,
                                modifier = Modifier.weight(1f), style = MaterialTheme.typography.titleSmall,
                                color = if (failed) scheme.onErrorContainer else textPrimary)
                            if (state.taskRunning) Text("${state.taskProgress.coerceIn(0, 100)}%", color = scheme.primary,
                                style = MaterialTheme.typography.titleSmall)
                            LuoShuGlyph(Icons.Rounded.ChevronRight, null, LuoShuIconTokens.TrailingGlyph, tint = textSecondary)
                        }
                        Text(if (failed) state.error else next.description,
                            color = if (failed) scheme.onErrorContainer else textSecondary,
                            style = MaterialTheme.typography.bodySmall)
                        if (state.taskRunning) LinearProgressIndicator(
                            progress = { state.taskProgress.coerceIn(0, 100) / 100f },
                            modifier = Modifier.fillMaxWidth().height(5.dp).clip(CircleShape),
                        )
                    }
                }
            }
        }
        item(key = "font-actions") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                LuoShuSectionHeading("我的字体", "个性化字形配置")
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    HomeShortcut("字体库", "导入 · 预览 · 应用", Icons.Rounded.FontDownload, actions.openFontLibrary,
                        Modifier.weight(1f))
                    HomeShortcut("字体组合", "中文 · 英文 · 数字", Icons.Rounded.Layers, actions.openFontStudio,
                        Modifier.weight(1f))
                }
            }
        }
        item(key = "weight") {
            SystemWeightCard(state.systemWeight.copy(applying = state.systemWeight.applying || state.taskRunning), actions, cardColor, textPrimary, textSecondary, shape)
        }
        item(key = "device-details") {
            Surface(shape = shape, color = cardColor) {
                Column(Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.fillMaxWidth()
                            .semantics { stateDescription = if (deviceDetailsExpanded) "已展开" else "已收起" }
                            .clickable(role = Role.Button) { deviceDetailsExpanded = !deviceDetailsExpanded }
                            .padding(18.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        LuoShuGlyph(Icons.Rounded.Security, null, LuoShuIconTokens.StatusGlyph, tint = scheme.primary)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                            Text("设备与生效状态", style = MaterialTheme.typography.titleSmall, color = textPrimary)
                            Text(if (state.rootGranted && state.mountHealthy) "${state.rootManager} · 挂载正常" else "查看权限、挂载与字体检查",
                                style = MaterialTheme.typography.bodySmall, color = textSecondary)
                        }
                        LuoShuGlyph(if (deviceDetailsExpanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                            null, LuoShuIconTokens.ToolGlyph, tint = textSecondary)
                    }
                    AnimatedVisibility(visible = deviceDetailsExpanded) {
                        Column(Modifier.padding(start = 14.dp, end = 14.dp, bottom = 18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                CompactStatusCell(Modifier.weight(1f), Icons.Rounded.Security, "Root",
                                    if (state.rootGranted) state.rootManager else "未授权", state.rootGranted, textPrimary, textSecondary)
                                CompactStatusCell(Modifier.weight(1f), Icons.Rounded.Layers, "挂载",
                                    state.mountEngine, state.mountHealthy, textPrimary, textSecondary)
                            }
                            trustContent()
                        }
                    }
                }
            }
        }
        item(key = "restore") {
            OutlinedButton(
                onClick = actions.restoreDefault,
                enabled = canChange,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                shape = RoundedCornerShape(18.dp),
            ) {
                LuoShuGlyph(Icons.Rounded.RestartAlt, null, LuoShuIconTokens.ToolGlyph)
                Spacer(Modifier.width(8.dp))
                Text("恢复系统字体")
            }
        }
    }
}

@Composable
private fun HomeShortcut(title: String, subtitle: String, icon: ImageVector, onClick: () -> Unit, modifier: Modifier) {
    val tokens = LocalMiuixTokens.current
    Surface(
        onClick = onClick,
        modifier = modifier,
        shape = RoundedCornerShape(24.dp),
        color = tokens.cardBackground,
        shadowElevation = 1.dp,
    ) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Surface(shape = RoundedCornerShape(15.dp), color = tokens.elevatedCardBackground) {
                Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
                    LuoShuGlyph(icon, null, LuoShuIconTokens.StatusGlyph, tint = MaterialTheme.colorScheme.primary)
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, color = tokens.textPrimary, style = MaterialTheme.typography.titleMedium)
                Text(subtitle, color = tokens.textSecondary, style = MaterialTheme.typography.bodySmall)
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
    !state.moduleInstalled || !state.rootGranted -> HomeNextStep(
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
                    tint = accent,
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        Column(Modifier.weight(1f)) {
            Text(
                value,
                color = textPrimary,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                "$title · ${if (healthy) "正常" else "需检查"}",
                color = if (healthy) textSecondary else accent,
                fontSize = 13.sp,
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
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(40.dp),
                    shape = RoundedCornerShape(14.dp),
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
                    Text("全局粗细微调", color = textPrimary, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                    Text("轻量显示微调 · 可随时恢复", color = textSecondary, fontSize = 11.sp)
                }
            }
            Spacer(Modifier.height(12.dp))
            when {
                weight.loading -> {
                    LuoShuLoadingSkeleton(
                        Modifier.fillMaxWidth(.28f).height(28.dp),
                        shape = RoundedCornerShape(10.dp),
                    )
                    Spacer(Modifier.height(10.dp))
                    LuoShuLoadingSkeleton(
                        Modifier.fillMaxWidth().height(42.dp),
                        shape = RoundedCornerShape(18.dp),
                    )
                }
                !weight.supported -> Text(
                    weight.error.ifBlank { "当前系统不支持全局粗细微调" },
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 12.sp,
                )
                else -> {
                    Text(
                        weight.weight.toString(),
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 28.sp,
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.titleLarge.copy(fontFeatureSettings = "tnum"),
                    )
                    Spacer(Modifier.height(6.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        WeightStepButton(
                            increase = false,
                            enabled = !weight.applying && weight.weight > weight.min,
                            onStep = {
                                actions.previewSystemWeight(
                                    (weight.weight - weight.step).coerceAtLeast(weight.min).toFloat(),
                                )
                            },
                        )
                        Slider(
                            value = weight.weight.toFloat(),
                            onValueChange = actions.previewSystemWeight,
                            modifier = Modifier.weight(1f).padding(horizontal = 10.dp),
                            enabled = !weight.applying,
                            valueRange = weight.min.toFloat()..weight.max.toFloat(),
                            steps = 0,
                        )
                        WeightStepButton(
                            increase = true,
                            enabled = !weight.applying && weight.weight < weight.max,
                            onStep = {
                                actions.previewSystemWeight(
                                    (weight.weight + weight.step).coerceAtMost(weight.max).toFloat(),
                                )
                            },
                        )
                    }
                    Row(Modifier.fillMaxWidth()) {
                        Text(
                            weight.min.toString(),
                            color = textSecondary,
                            fontSize = 11.sp,
                            style = MaterialTheme.typography.labelSmall.copy(fontFeatureSettings = "tnum"),
                        )
                        Spacer(Modifier.weight(1f))
                        Text(
                            weight.max.toString(),
                            color = textSecondary,
                            fontSize = 11.sp,
                            style = MaterialTheme.typography.labelSmall.copy(fontFeatureSettings = "tnum"),
                        )
                    }
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

@Composable
private fun WeightStepButton(
    increase: Boolean,
    enabled: Boolean,
    onStep: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    Surface(
        modifier = Modifier
            .size(42.dp)
            .clip(RoundedCornerShape(14.dp))
            .pointerInput(enabled, onStep) {
                detectTapGestures(
                    onPress = {
                        if (!enabled) return@detectTapGestures
                        onStep()
                        coroutineScope {
                            val repeatJob = launch {
                                delay(430)
                                while (true) {
                                    onStep()
                                    delay(85)
                                }
                            }
                            tryAwaitRelease()
                            repeatJob.cancel()
                        }
                    },
                )
            },
        shape = RoundedCornerShape(14.dp),
        color = if (enabled) scheme.surfaceContainerHigh else scheme.surfaceContainerLow,
        contentColor = if (enabled) scheme.primary else scheme.onSurfaceVariant.copy(alpha = .38f),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(
                if (increase) Icons.Rounded.Add else Icons.Rounded.Remove,
                contentDescription = if (increase) "加粗一步" else "变细一步",
                modifier = Modifier.size(20.dp),
            )
        }
    }
}
