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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import kotlin.math.roundToInt
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.CircularProgressIndicator
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.LinearProgressIndicator
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun FontStudioScreenMiuixNative(
    state: FontStudioUiState,
    actions: FontStudioActions,
    topAction: @Composable () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background),
        contentPadding = PaddingValues(start = 16.dp, top = 18.dp, end = 16.dp, bottom = 112.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        text = "字体组合",
                        fontSize = 34.sp,
                        fontWeight = FontWeight.Bold,
                        color = colors.onBackground,
                    )
                    Text(
                        text = "中文、英文、数字与真实设计轴",
                        fontSize = 14.sp,
                        color = colors.onSurfaceSecondary,
                    )
                }
                topAction()
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = actions.refresh,
                    enabled = !state.loading,
                ) {
                    if (state.loading) {
                        CircularProgressIndicator(
                            progress = null,
                            modifier = Modifier.size(20.dp),
                        )
                    } else {
                        Icon(
                            imageVector = Icons.Rounded.Refresh,
                            contentDescription = null,
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }
        }

        if (state.error.isNotBlank()) {
            item {
                MiuixStudioNoticeNative(
                    title = "字体组合需要处理",
                    message = state.error,
                    icon = Icons.Rounded.Warning,
                    error = true,
                )
            }
        }
        if (state.busy || state.taskState == "success") {
            item { MiuixStudioTaskNative(state) }
        }

        item { MiuixCompositionMapNative(state) }

        state.slots.forEach { slotState ->
            item(key = "native-${slotState.slot.name}") {
                MiuixStudioSlotNative(
                    slotState = slotState,
                    busy = state.busy || state.operationBusy,
                    actions = actions,
                )
            }
        }

        item { MiuixCoverageNative(state, actions) }
        item { MiuixFinalActionNative(state, actions) }
    }
}

@Composable
private fun MiuixCompositionMapNative(state: FontStudioUiState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = "组合结构",
            summary = "三个槽位独立预览，最终输出统一生成",
            startAction = { MiuixStudioIconNative(Icons.Rounded.AutoAwesome) },
        )
        state.slots.forEach { slot ->
            BasicComponent(
                title = slot.title,
                summary = slot.font?.name ?: "未选择字体",
                startAction = {
                    MiuixSlotPreviewNative(slot)
                },
            )
        }
    }
}

@Composable
private fun MiuixSlotPreviewNative(slot: StudioSlotUiState) {
    val font = slot.font
    Box(
        modifier = Modifier
            .padding(end = 16.dp)
            .size(46.dp)
            .background(MiuixTheme.colorScheme.tertiaryContainer, RoundedCornerShape(16.dp)),
        contentAlignment = Alignment.Center,
    ) {
        if (font != null && font.valid) {
            NativeFontPreview(
                font = font,
                text = slotPreviewText(slot.slot),
                axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                modifier = Modifier.size(46.dp).padding(5.dp),
                textSizeSp = 16f,
                gravity = Gravity.CENTER,
                maxLines = 1,
            )
        } else {
            Text(
                text = slotPreviewText(slot.slot),
                color = MiuixTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun MiuixStudioSlotNative(
    slotState: StudioSlotUiState,
    busy: Boolean,
    actions: FontStudioActions,
) {
    val colors = MiuixTheme.colorScheme
    val font = slotState.font
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = slotState.title,
            summary = buildString {
                append(slotState.subtitle)
                if (font != null) append("\n${fontCapabilityLabel(font)}")
            },
            startAction = { MiuixSlotPreviewNative(slotState) },
            enabled = !busy,
            onClick = { actions.pickSlot(slotState.slot) },
        )

        if (font == null) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                Button(
                    onClick = { actions.pickSlot(slotState.slot) },
                    enabled = !busy,
                ) {
                    Text("选择字体", fontWeight = FontWeight.Bold)
                }
            }
            return@Card
        }

        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column {
                Text(
                    text = font.name,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    color = colors.onBackground,
                )
                Text(
                    text = font.format,
                    color = colors.onSurfaceSecondary,
                    fontSize = 11.sp,
                )
            }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(86.dp)
                    .background(colors.surfaceContainer, RoundedCornerShape(22.dp)),
                contentAlignment = Alignment.Center,
            ) {
                NativeFontPreview(
                    font = font,
                    text = slotState.sample,
                    axes = slotState.axes,
                    modifier = Modifier.fillMaxWidth().height(86.dp).padding(horizontal = 14.dp),
                    textSizeSp = 25f,
                    gravity = Gravity.CENTER,
                    maxLines = 1,
                )
            }

            StudioAxisControlsMiuix(
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

@Composable
private fun MiuixStudioTaskNative(state: FontStudioUiState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = if (state.busy) "复合任务执行中" else "复合字体已生成",
            summary = state.message,
            startAction = {
                if (state.busy) {
                    CircularProgressIndicator(
                        progress = null,
                        modifier = Modifier.padding(end = 16.dp).size(24.dp),
                    )
                } else {
                    MiuixStudioIconNative(Icons.Rounded.CheckCircle)
                }
            },
        )
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
            LinearProgressIndicator(
                progress = state.progress.coerceIn(0, 100) / 100f,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = "${state.progress}%",
                color = MiuixTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.align(Alignment.End),
            )
        }
    }
}

@Composable
private fun MiuixCoverageNative(
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    val colors = MiuixTheme.colorScheme
    val cjk = state.slots.firstOrNull { it.slot == MixSlot.Cjk }
    val fontId = cjk?.font?.id.orEmpty()
    val probe = state.coverage
    val metrics = probe.metrics.takeIf { probe.fontId == fontId }

    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = "字形覆盖诊断",
            summary = cjk?.font?.name ?: "请先选择中文基底",
            startAction = { MiuixStudioIconNative(Icons.Rounded.CheckCircle) },
        )
        Column(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Button(
                onClick = { actions.inspectCoverage(fontId) },
                enabled = fontId.isNotBlank() && !probe.loading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (probe.loading) {
                    CircularProgressIndicator(
                        progress = null,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text(if (probe.loading) "正在检测" else "检测字形覆盖", fontWeight = FontWeight.Bold)
            }

            if (metrics != null) {
                MiuixCoverageRowNative("中文", metrics.cjkRatio)
                MiuixCoverageRowNative("英文", metrics.latinRatio)
                MiuixCoverageRowNative("数字", metrics.digitRatio)
                MiuixCoverageRowNative("标点", metrics.punctuationRatio)
                if (metrics.missingSample.isNotBlank()) {
                    Text(
                        text = "缺失示例：${metrics.missingSample}",
                        color = colors.onSurfaceSecondary,
                        fontSize = 11.sp,
                    )
                }
            } else if (probe.error.isNotBlank() && probe.fontId == fontId) {
                Text(
                    text = probe.error,
                    color = colors.error,
                    fontSize = 12.sp,
                )
            }
        }
    }
}

@Composable
private fun MiuixCoverageRowNative(label: String, ratio: Float) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            modifier = Modifier.width(42.dp),
            fontWeight = FontWeight.Bold,
            color = MiuixTheme.colorScheme.onBackground,
        )
        LinearProgressIndicator(
            progress = ratio.coerceIn(0f, 1f),
            modifier = Modifier.weight(1f),
        )
        Spacer(Modifier.width(10.dp))
        Text(
            text = "${(ratio * 100).roundToInt()}%",
            color = MiuixTheme.colorScheme.primary,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun MiuixFinalActionNative(
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    val direct = state.directApplyFontId
    val enabled = !state.busy && !state.operationBusy && state.hasFonts
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = if (direct != null) "同一字体，无需复合" else "生成完整复合字体",
            summary = if (direct != null) {
                "三个槽位保持标准 Regular 400，将直接应用原始字体"
            } else {
                "真实字重和全部设计轴会写入最终字体文件"
            },
            startAction = {
                MiuixStudioIconNative(
                    if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome,
                )
            },
        )
        Button(
            onClick = {
                if (direct != null) actions.applyDirect(direct) else actions.startMix()
            },
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
        ) {
            Icon(
                imageVector = if (direct != null) Icons.Rounded.FontDownload else Icons.Rounded.AutoAwesome,
                contentDescription = null,
                modifier = Modifier.size(21.dp),
            )
            Text(
                text = if (direct != null) "直接应用此字体" else "生成并应用到系统",
                modifier = Modifier.padding(start = 8.dp),
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun MiuixStudioNoticeNative(
    title: String,
    message: String,
    icon: ImageVector,
    error: Boolean,
) {
    val colors = MiuixTheme.colorScheme
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = title,
            summary = message,
            startAction = {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = if (error) colors.error else colors.primary,
                    modifier = Modifier.padding(end = 16.dp).size(24.dp),
                )
            },
        )
    }
}

@Composable
private fun MiuixStudioIconNative(icon: ImageVector) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = MiuixTheme.colorScheme.primary,
        modifier = Modifier.padding(end = 16.dp).size(24.dp),
    )
}

private fun slotPreviewText(slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> "中"
    MixSlot.Latin -> "Aa"
    MixSlot.Digit -> "123"
}
