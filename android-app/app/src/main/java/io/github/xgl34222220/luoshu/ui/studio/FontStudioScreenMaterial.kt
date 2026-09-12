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
import androidx.compose.foundation.layout.heightIn
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
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSectionHeading
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTopBar
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import kotlin.math.roundToInt

@Composable
internal fun FontStudioScreenMaterial(
    state: FontStudioUiState,
    actions: FontStudioActions,
    topAction: @Composable () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, bottom = maxOf(LocalDockContentPadding.current, 28.dp)),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        item { MaterialStudioHeader(state.loading, actions.refresh, topAction) }
        item { MaterialCompositionOverview(state, actions) }

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
                MaterialSlotCard(slotState, state.busy || state.operationBusy, actions)
            }
        }

        item { MaterialFinalAction(state, actions) }
        item { LuoShuSectionHeading("字形覆盖", "需要时查看所选中文字体包含哪些字符") }
        item { MaterialCoverageCard(state, actions) }
    }
}

@Composable
private fun MaterialStudioHeader(loading: Boolean, onRefresh: () -> Unit, topAction: @Composable () -> Unit) {
    val actionColor = MaterialTheme.colorScheme.primary
    LuoShuTopBar(title = "字体组合") {
        Row(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            topAction()
            LuoShuHeaderAction(
                icon = Icons.Rounded.Refresh,
                contentDescription = "刷新组合配置",
                onClick = onRefresh,
                enabled = !loading,
                loading = loading,
                containerColor = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .84f),
                contentColor = actionColor,
            )
        }
    }
}

@Composable
private fun MaterialCompositionOverview(state: FontStudioUiState, actions: FontStudioActions) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(Modifier.padding(20.dp)) {
            Text("组合你的专属字体", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            Text("中文、英文、数字，分别挑选喜欢的样子。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
            Spacer(Modifier.height(15.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                state.slots.forEach { slot ->
                    MaterialSlotSummary(slot, Modifier.weight(1f), !state.busy && !state.operationBusy) { actions.pickSlot(slot.slot) }
                }
            }
        }
    }
}

@Composable
private fun MaterialSlotSummary(slot: StudioSlotUiState, modifier: Modifier, enabled: Boolean, onSelect: () -> Unit) {
    Surface(
        onClick = onSelect,
        enabled = enabled,
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
                fontSize = 24.sp,
                fontWeight = FontWeight.Medium,
            )
            Spacer(Modifier.height(6.dp))
            Text(slot.title, fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Text(
                slot.font?.name ?: "未选择",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
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
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = MaterialTheme.colorScheme.secondary)
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(if (state.busy) "正在生成组合字体" else "组合字体已生成", fontWeight = FontWeight.SemiBold)
                    Text(state.message, color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = .74f), fontSize = 12.sp)
                }
                Text("${state.progress}%", color = MaterialTheme.colorScheme.secondary, fontWeight = FontWeight.SemiBold)
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
        Column(Modifier.padding(20.dp)) {
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
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(slotState.title, fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
                    Text(slotState.subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
            }
            if (font != null) {
                Spacer(Modifier.height(10.dp))
                MaterialStudioPill(fontCapabilityLabel(font), MaterialTheme.colorScheme.primary)
            }

            Spacer(Modifier.height(14.dp))
            OutlinedButton(
                onClick = { actions.pickSlot(slotState.slot) },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp),
                shape = MaterialTheme.shapes.large,
            ) {
                Text(
                    font?.name ?: "点此选择字体",
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
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("所选字体覆盖率", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Text(cjk?.font?.name ?: "请先选择中文基底", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = { actions.inspectCoverage(fontId) },
                    enabled = fontId.isNotBlank() && !probe.loading && !state.busy && !state.operationBusy,
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
                    Text("缺失示例：${metrics.missingSample}", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                }
            } else if (probe.error.isNotBlank() && probe.fontId == fontId) {
                Spacer(Modifier.height(10.dp))
                Text(probe.error, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun MaterialCoverageRow(label: String, ratio: Float) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.width(42.dp), fontSize = 12.sp, fontWeight = FontWeight.Bold)
        LinearProgressIndicator(
            progress = { ratio },
            modifier = Modifier.weight(1f).height(7.dp),
        )
        Spacer(Modifier.width(10.dp))
        Text("${(ratio * 100).roundToInt()}%", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun MaterialFinalAction(state: FontStudioUiState, actions: FontStudioActions) {
    val direct = state.directApplyFontId
    val selectionReady = state.slots.size == MixSlot.entries.size && state.slots.all { it.font?.valid == true }
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
                    Text(if (direct != null) "准备应用" else "让这个组合成为日常", fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                    Text(
                        if (direct != null) "三个部分使用同一款字体，可直接应用。"
                        else "按上面的字体和字重生成组合，然后应用到系统。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 12.sp,
                    )
                }
            }
            Spacer(Modifier.height(17.dp))
            Button(
                onClick = { if (direct != null) actions.applyDirect(direct) else actions.startMix() },
                enabled = !state.loading && !state.busy && !state.operationBusy && selectionReady,
                modifier = Modifier.fillMaxWidth().heightIn(min = 60.dp),
                shape = MaterialTheme.shapes.large,
            ) {
                Icon(if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(
                    if (state.busy || state.operationBusy) "正在处理，请稍候…"
                    else if (!selectionReady) "先选择组合字体"
                    else if (direct != null) "直接应用此字体" else "生成并应用",
                    fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                )
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
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
