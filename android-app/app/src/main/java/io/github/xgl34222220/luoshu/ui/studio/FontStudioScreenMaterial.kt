package io.github.xgl34222220.luoshu.ui.studio

import android.view.Gravity
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CheckCircle
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import kotlin.math.roundToInt

@Composable
internal fun FontStudioScreenMaterial(
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialStudioHeader(state.loading, actions.refresh) }
        item { MaterialCompositionOverview(state) }

        if (state.loading) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth().height(4.dp)) }
        }
        if (state.error.isNotBlank()) {
            item { MaterialStudioNotice(state.error, error = true) }
        }
        if (state.busy || state.taskState == "success") {
            item { MaterialStudioTask(state) }
        }

        state.slots.forEach { slotState ->
            item(key = slotState.slot.name) {
                MaterialSlotCard(slotState, state.busy, actions)
            }
        }

        item { MaterialCoverageCard(state, actions) }
        item { MaterialFinalAction(state, actions) }
    }
}

@Composable
private fun MaterialStudioHeader(loading: Boolean, onRefresh: () -> Unit) {
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
                letterSpacing = 2.2.sp,
            )
            Spacer(Modifier.height(4.dp))
            Text("字体组合", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Black)
            Text("中文、英文、数字与完整设计轴", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
        }
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .84f),
            shadowElevation = 7.dp,
        ) {
            IconButton(onClick = onRefresh, enabled = !loading, modifier = Modifier.size(56.dp)) {
                if (loading) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                else Icon(Icons.Rounded.Refresh, contentDescription = "刷新组合配置")
            }
        }
    }
}

@Composable
private fun MaterialCompositionOverview(state: FontStudioUiState) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(18.dp)) {
            Text("组合结构", fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text("三个槽位只共享最终输出，不共享预览缓存", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            Spacer(Modifier.height(15.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                state.slots.forEach { slot ->
                    MaterialSlotSummary(slot, Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun MaterialSlotSummary(slot: StudioSlotUiState, modifier: Modifier) {
    Surface(
        modifier = modifier,
        shape = MaterialTheme.shapes.large,
        color = if (slot.font == null) MaterialTheme.colorScheme.surfaceContainerHigh
        else MaterialTheme.colorScheme.primaryContainer,
    ) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 12.dp)) {
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
            Spacer(Modifier.height(6.dp))
            Text(slot.title, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Text(
                slot.font?.name ?: "未选择",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 9.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun MaterialStudioTask(state: FontStudioUiState) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (state.busy) "复合字体任务执行中" else "复合字体已生成", fontWeight = FontWeight.Black)
                    Text(state.message, color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = .74f), fontSize = 11.sp)
                }
                Text("${state.progress}%", color = MaterialTheme.colorScheme.secondary, fontWeight = FontWeight.Black)
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
private fun MaterialSlotCard(
    slotState: StudioSlotUiState,
    busy: Boolean,
    actions: FontStudioActions,
) {
    val font = slotState.font
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(50.dp),
                    shape = MaterialTheme.shapes.large,
                    color = MaterialTheme.colorScheme.primaryContainer,
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
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(slotState.title, fontSize = 19.sp, fontWeight = FontWeight.Black)
                    Text(slotState.subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                }
                if (font != null) {
                    MaterialStudioPill(fontCapabilityLabel(font), MaterialTheme.colorScheme.primary)
                }
            }

            Spacer(Modifier.height(14.dp))
            OutlinedButton(
                onClick = { actions.pickSlot(slotState.slot) },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth().height(54.dp),
                shape = MaterialTheme.shapes.large,
            ) {
                Text(
                    font?.name ?: "选择字体",
                    modifier = Modifier.weight(1f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    fontWeight = FontWeight.Bold,
                )
                Icon(Icons.Rounded.KeyboardArrowDown, contentDescription = null)
            }

            if (font != null) {
                Spacer(Modifier.height(13.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = MaterialTheme.shapes.large,
                    color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .62f),
                ) {
                    NativeFontPreview(
                        font = font,
                        text = slotState.sample,
                        axes = slotState.axes,
                        modifier = Modifier.fillMaxWidth().height(82.dp).padding(horizontal = 15.dp),
                        textSizeSp = 25f,
                        gravity = Gravity.CENTER,
                        maxLines = 1,
                    )
                }
                Spacer(Modifier.height(14.dp))
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f))
                Spacer(Modifier.height(14.dp))
                MaterialStudioAxisControls(
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
private fun MaterialCoverageCard(state: FontStudioUiState, actions: FontStudioActions) {
    val cjk = state.slots.firstOrNull { it.slot == MixSlot.Cjk }
    val fontId = cjk?.font?.id.orEmpty()
    val probe = state.coverage
    val metrics = probe.metrics.takeIf { probe.fontId == fontId }
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("字形覆盖诊断", fontSize = 18.sp, fontWeight = FontWeight.Black)
                    Text(cjk?.font?.name ?: "请先选择中文基底", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                }
                OutlinedButton(
                    onClick = { actions.inspectCoverage(fontId) },
                    enabled = fontId.isNotBlank() && !probe.loading,
                ) {
                    if (probe.loading) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                    else Text("检测")
                }
            }
            if (metrics != null) {
                Spacer(Modifier.height(13.dp))
                MaterialCoverageRow("中文", metrics.cjkRatio)
                MaterialCoverageRow("英文", metrics.latinRatio)
                MaterialCoverageRow("数字", metrics.digitRatio)
                MaterialCoverageRow("标点", metrics.punctuationRatio)
                if (metrics.missingSample.isNotBlank()) {
                    Spacer(Modifier.height(8.dp))
                    Text("缺失示例：${metrics.missingSample}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
                }
            } else if (probe.error.isNotBlank() && probe.fontId == fontId) {
                Spacer(Modifier.height(10.dp))
                Text(probe.error, color = MaterialTheme.colorScheme.error, fontSize = 11.sp)
            }
        }
    }
}

@Composable
private fun MaterialCoverageRow(label: String, ratio: Float) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.width(42.dp), fontSize = 11.sp, fontWeight = FontWeight.Bold)
        LinearProgressIndicator(
            progress = { ratio },
            modifier = Modifier.weight(1f).height(7.dp),
        )
        Spacer(Modifier.width(10.dp))
        Text("${(ratio * 100).roundToInt()}%", color = MaterialTheme.colorScheme.primary, fontSize = 11.sp, fontWeight = FontWeight.Black)
    }
}

@Composable
private fun MaterialFinalAction(state: FontStudioUiState, actions: FontStudioActions) {
    val direct = state.directApplyFontId
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.primaryContainer,
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
                    Text(if (direct != null) "同一字体，无需复合" else "生成完整复合字体", fontSize = 18.sp, fontWeight = FontWeight.Black)
                    Text(
                        if (direct != null) "三个槽位均为标准 Regular 400，将直接应用原始字体。"
                        else "当前真实字重与全部设计轴会写入最终字体。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                    )
                }
            }
            Spacer(Modifier.height(17.dp))
            Button(
                onClick = { if (direct != null) actions.applyDirect(direct) else actions.startMix() },
                enabled = !state.busy && !state.operationBusy && state.hasFonts,
                modifier = Modifier.fillMaxWidth().height(60.dp),
                shape = MaterialTheme.shapes.large,
            ) {
                Icon(if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(if (direct != null) "直接应用此字体" else "生成并应用到系统", fontSize = 16.sp, fontWeight = FontWeight.Black)
            }
        }
    }
}

@Composable
private fun MaterialStudioNotice(message: String, error: Boolean) {
    Surface(
        shape = MaterialTheme.shapes.large,
        color = if (error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer,
    ) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(
                if (error) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                contentDescription = null,
                tint = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.secondary,
            )
            Spacer(Modifier.width(10.dp))
            Text(message, modifier = Modifier.weight(1f), fontSize = 12.sp)
        }
    }
}

@Composable
private fun MaterialStudioPill(text: String, color: Color) {
    Surface(shape = CircleShape, color = color.copy(alpha = .12f)) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
        )
    }
}
