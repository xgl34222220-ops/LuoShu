package io.github.xgl34222220.luoshu.ui.studio

import android.view.Gravity
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.KeyboardArrowDown
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import kotlin.math.roundToInt

@Composable
internal fun FontStudioScreenMiuix(
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MiuixStudioHeader(state.loading, actions.refresh) }
        item { MiuixCompositionMap(state) }

        if (state.loading) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth().height(4.dp)) }
        }
        if (state.error.isNotBlank()) {
            item { MiuixStudioNotice(state.error, error = true) }
        }
        if (state.busy || state.taskState == "success") {
            item { MiuixStudioTask(state) }
        }

        state.slots.forEach { slotState ->
            item(key = slotState.slot.name) {
                MiuixSlotCard(slotState, state.busy, actions)
            }
        }

        item { MiuixCoverageGroup(state, actions) }
        item { MiuixFinalAction(state, actions) }
    }
}

@Composable
private fun MiuixStudioHeader(loading: Boolean, onRefresh: () -> Unit) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                "FONT MIX",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.4.sp,
            )
            Spacer(Modifier.height(3.dp))
            Text(
                "字体组合",
                color = tokens.textPrimary,
                fontSize = 42.sp,
                lineHeight = 47.sp,
                fontWeight = FontWeight.Black,
            )
            Text("中文、英文、数字与真实设计轴", color = tokens.textSecondary, fontSize = 12.sp)
        }
        Card(
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = tokens.elevatedCardBackground),
            elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
        ) {
            IconButton(onClick = onRefresh, enabled = !loading, modifier = Modifier.size(56.dp)) {
                if (loading) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                else Icon(Icons.Rounded.Refresh, contentDescription = "刷新组合配置")
            }
        }
    }
}

@Composable
private fun MiuixCompositionMap(state: FontStudioUiState) {
    val tokens = LocalMiuixTokens.current
    val shape = RoundedCornerShape(36.dp)
    Card(
        modifier = Modifier.fillMaxWidth().shadow(9.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.verticalGradient(
                        listOf(
                            MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                            Color.Transparent,
                        ),
                    ),
                )
                .padding(19.dp),
        ) {
            Text("组合结构", color = tokens.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Black)
            Text("三个槽位独立预览，最终输出统一生成", color = tokens.textSecondary, fontSize = 11.sp)
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                state.slots.forEach { slot ->
                    MiuixSlotSummary(slot, Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun MiuixSlotSummary(slot: StudioSlotUiState, modifier: Modifier) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(22.dp),
        color = if (slot.font == null) tokens.textPrimary.copy(alpha = .045f)
        else MaterialTheme.colorScheme.primary.copy(alpha = .11f),
    ) {
        Column(Modifier.padding(horizontal = 11.dp, vertical = 12.dp)) {
            Text(
                when (slot.slot) {
                    MixSlot.Cjk -> "中"
                    MixSlot.Latin -> "Aa"
                    MixSlot.Digit -> "123"
                },
                color = MaterialTheme.colorScheme.primary,
                fontSize = 18.sp,
                fontWeight = FontWeight.Black,
            )
            Spacer(Modifier.height(5.dp))
            Text(slot.title, color = tokens.textPrimary, fontSize = 10.sp, fontWeight = FontWeight.Black)
            Text(
                slot.font?.name ?: "未选择",
                color = tokens.textSecondary,
                fontSize = 9.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun MiuixStudioTask(state: FontStudioUiState) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(32.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(44.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (state.busy) "复合任务执行中" else "复合字体已生成",
                        color = tokens.textPrimary,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(state.message, color = tokens.textSecondary, fontSize = 11.sp)
                }
                MiuixStudioPill("${state.progress}%", MaterialTheme.colorScheme.primary)
            }
            Spacer(Modifier.height(13.dp))
            LinearProgressIndicator(
                progress = { state.progress.coerceIn(0, 100) / 100f },
                modifier = Modifier.fillMaxWidth().height(7.dp),
            )
        }
    }
}

@Composable
private fun MiuixSlotCard(
    slotState: StudioSlotUiState,
    busy: Boolean,
    actions: FontStudioActions,
) {
    val tokens = LocalMiuixTokens.current
    val font = slotState.font
    val shape = RoundedCornerShape(36.dp)
    Card(
        modifier = Modifier.fillMaxWidth().shadow(7.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
    ) {
        Column(Modifier.padding(horizontal = 17.dp, vertical = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = RoundedCornerShape(17.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            when (slotState.slot) {
                                MixSlot.Cjk -> "中"
                                MixSlot.Latin -> "Aa"
                                MixSlot.Digit -> "123"
                            },
                            color = MaterialTheme.colorScheme.primary,
                            fontWeight = FontWeight.Black,
                        )
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(slotState.title, color = tokens.textPrimary, fontSize = 19.sp, fontWeight = FontWeight.Black)
                    Text(slotState.subtitle, color = tokens.textSecondary, fontSize = 10.sp)
                }
                if (font != null) MiuixStudioPill(fontCapabilityLabel(font), MaterialTheme.colorScheme.primary)
            }

            Spacer(Modifier.height(13.dp))
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(enabled = !busy) { actions.pickSlot(slotState.slot) },
                shape = RoundedCornerShape(22.dp),
                color = tokens.textPrimary.copy(alpha = .04f),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 15.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            font?.name ?: "选择字体",
                            color = tokens.textPrimary,
                            fontWeight = FontWeight.Bold,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (font != null) {
                            Text(font.format, color = tokens.textSecondary, fontSize = 9.sp)
                        }
                    }
                    Icon(Icons.Rounded.KeyboardArrowDown, contentDescription = null, tint = tokens.textSecondary)
                }
            }

            if (font != null) {
                Spacer(Modifier.height(12.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(24.dp),
                    color = tokens.textPrimary.copy(alpha = .035f),
                ) {
                    NativeFontPreview(
                        font = font,
                        text = slotState.sample,
                        axes = slotState.axes,
                        modifier = Modifier.fillMaxWidth().height(78.dp).padding(horizontal = 14.dp),
                        textSizeSp = 25f,
                        gravity = Gravity.CENTER,
                        maxLines = 1,
                    )
                }
                Spacer(Modifier.height(13.dp))
                MiuixStudioAxisControls(
                    font = font,
                    weight = slotState.weight,
                    axes = slotState.axes,
                    enabled = !busy,
                    onWeight = { actions.updateWeight(slotState.slot, it) },
                    onAxis = { tag, value -> actions.updateAxis(slotState.slot, tag, value) },
                )
            }
        }
    }
}

@Composable
private fun MiuixCoverageGroup(state: FontStudioUiState, actions: FontStudioActions) {
    val tokens = LocalMiuixTokens.current
    val cjk = state.slots.firstOrNull { it.slot == MixSlot.Cjk }
    val fontId = cjk?.font?.id.orEmpty()
    val probe = state.coverage
    val metrics = probe.metrics.takeIf { probe.fontId == fontId }
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
    ) {
        Column(Modifier.padding(horizontal = 17.dp, vertical = 16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("字形覆盖诊断", color = tokens.textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Black)
                    Text(cjk?.font?.name ?: "请先选择中文基底", color = tokens.textSecondary, fontSize = 11.sp)
                }
                OutlinedButton(
                    onClick = { actions.inspectCoverage(fontId) },
                    enabled = fontId.isNotBlank() && !probe.loading,
                    shape = RoundedCornerShape(17.dp),
                ) {
                    if (probe.loading) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    else Text("检测")
                }
            }
            if (metrics != null) {
                Spacer(Modifier.height(12.dp))
                MiuixCoverageRow("中文", metrics.cjkRatio)
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .42f))
                MiuixCoverageRow("英文", metrics.latinRatio)
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .42f))
                MiuixCoverageRow("数字", metrics.digitRatio)
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .42f))
                MiuixCoverageRow("标点", metrics.punctuationRatio)
                if (metrics.missingSample.isNotBlank()) {
                    Spacer(Modifier.height(8.dp))
                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = tokens.textPrimary.copy(alpha = .035f),
                    ) {
                        Text(
                            "缺失示例：${metrics.missingSample}",
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 10.dp),
                            color = tokens.textSecondary,
                            fontSize = 9.sp,
                        )
                    }
                }
            } else if (probe.error.isNotBlank() && probe.fontId == fontId) {
                Spacer(Modifier.height(10.dp))
                Text(probe.error, color = MaterialTheme.colorScheme.error, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun MiuixCoverageRow(label: String, ratio: Float) {
    val tokens = LocalMiuixTokens.current
    Row(Modifier.fillMaxWidth().padding(vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = tokens.textPrimary, modifier = Modifier.width(42.dp), fontSize = 12.sp, fontWeight = FontWeight.Black)
        LinearProgressIndicator(
            progress = { ratio },
            modifier = Modifier.weight(1f).height(7.dp),
        )
        Spacer(Modifier.width(10.dp))
        Text("${(ratio * 100).roundToInt()}%", color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun MiuixFinalAction(state: FontStudioUiState, actions: FontStudioActions) {
    val tokens = LocalMiuixTokens.current
    val direct = state.directApplyFontId
    val shape = RoundedCornerShape(36.dp)
    Card(
        modifier = Modifier.fillMaxWidth().shadow(9.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
    ) {
        Column(Modifier.padding(19.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(50.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (direct != null) "同一字体，无需复合" else "生成完整复合字体",
                        color = tokens.textPrimary,
                        fontSize = 19.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        if (direct != null) "三个槽位保持标准 Regular 400，将直接应用原始字体。"
                        else "真实字重和全部设计轴会写入最终字体文件。",
                        color = tokens.textSecondary,
                        fontSize = 11.sp,
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(
                        enabled = !state.busy && !state.operationBusy && state.hasFonts,
                    ) {
                        if (direct != null) actions.applyDirect(direct) else actions.startMix()
                    },
                shape = RoundedCornerShape(22.dp),
                color = if (!state.busy && !state.operationBusy && state.hasFonts) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.surfaceVariant
                },
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().height(60.dp).padding(horizontal = 18.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
                    Icon(
                        if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome,
                        contentDescription = null,
                        tint = if (!state.busy && !state.operationBusy && state.hasFonts) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (direct != null) "直接应用此字体" else "生成并应用到系统",
                        color = if (!state.busy && !state.operationBusy && state.hasFonts) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Spacer(Modifier.width(4.dp))
                    Icon(
                        Icons.Rounded.ChevronRight,
                        contentDescription = null,
                        tint = if (!state.busy && !state.operationBusy && state.hasFonts) MaterialTheme.colorScheme.onPrimary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun MiuixStudioNotice(message: String, error: Boolean) {
    val tokens = LocalMiuixTokens.current
    Surface(
        shape = RoundedCornerShape(27.dp),
        color = if (error) MaterialTheme.colorScheme.errorContainer else tokens.cardBackground,
        shadowElevation = if (error) 0.dp else 4.dp,
    ) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(
                if (error) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                contentDescription = null,
                tint = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.width(10.dp))
            Text(
                message,
                modifier = Modifier.weight(1f),
                color = if (error) MaterialTheme.colorScheme.onErrorContainer else tokens.textPrimary,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun MiuixStudioPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .12f)) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
        )
    }
}
