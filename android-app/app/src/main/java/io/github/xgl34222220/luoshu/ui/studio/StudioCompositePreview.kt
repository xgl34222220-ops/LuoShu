package io.github.xgl34222220.luoshu.ui.studio

import android.view.Gravity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

internal enum class StudioPreviewScenario(val label: String) {
    MIXED("混排"),
    BODY("正文"),
    INTERFACE("界面"),
    NUMBERS("金额"),
}

internal data class StudioQuickPreset(
    val id: String,
    val label: String,
    val description: String,
    val cjkWeight: Int,
    val latinWeight: Int,
    val digitWeight: Int,
)

internal val studioQuickPresets = listOf(
    StudioQuickPreset("balanced", "均衡", "三种文字保持一致视觉重量", 400, 400, 400),
    StudioQuickPreset("reading", "正文", "中文与英文自然，数字稍加强", 400, 400, 500),
    StudioQuickPreset("headline", "标题", "适合标题、桌面和设置页", 600, 600, 600),
    StudioQuickPreset("numbers", "数字强化", "金额、时间和状态数字更醒目", 400, 400, 650),
)

internal fun StudioQuickPreset.weightFor(slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> cjkWeight
    MixSlot.Latin -> latinWeight
    MixSlot.Digit -> digitWeight
}

@Composable
internal fun StudioPreviewLauncher(
    style: UiStyle,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 18.dp),
        color = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh,
        contentColor = MaterialTheme.colorScheme.primary,
        shadowElevation = 8.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 15.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.AutoAwesome, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("组合预览", fontSize = 12.sp, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
internal fun StudioCompositePreviewDialog(
    style: UiStyle,
    state: FontStudioUiState,
    onApplyPreset: (StudioQuickPreset) -> Unit,
    onDismiss: () -> Unit,
) {
    var scenarioName by rememberSaveable { mutableStateOf(StudioPreviewScenario.MIXED.name) }
    val scenario = remember(scenarioName) {
        StudioPreviewScenario.entries.firstOrNull { it.name == scenarioName } ?: StudioPreviewScenario.MIXED
    }
    val tokens = LocalMiuixTokens.current
    val miuix = style == UiStyle.MIUIX
    val container = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh

    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(if (miuix) 34.dp else 28.dp),
        containerColor = container,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("最终组合预览", fontWeight = FontWeight.Black)
                    Text(
                        "切换场景，对照系统字体并快速调整三个槽位",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                }
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Rounded.Close, contentDescription = "关闭")
                }
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 590.dp)
                    .verticalScroll(rememberScrollState()),
            ) {
                PreviewScenarioSelector(
                    selected = scenario,
                    onSelect = { scenarioName = it.name },
                )
                Spacer(Modifier.height(14.dp))
                PreviewReferenceCard(style, scenario)
                Spacer(Modifier.height(12.dp))
                PreviewCandidateCard(style, state, scenario)
                Spacer(Modifier.height(15.dp))
                Text("快速方案", fontSize = 16.sp, fontWeight = FontWeight.Black)
                Text(
                    "只调整当前三个槽位的字重，不更换你已选择的字体。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                )
                Spacer(Modifier.height(9.dp))
                QuickPresetGrid(
                    style = style,
                    enabled = !state.busy && !state.operationBusy,
                    onApplyPreset = onApplyPreset,
                )
                Spacer(Modifier.height(13.dp))
                Surface(
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                ) {
                    Text(
                        "这里是槽位级合成模拟，用于判断视觉重量、混排比例和基线关系；最终字形覆盖与系统加载结果仍以生成任务和开机验证为准。",
                        modifier = Modifier.fillMaxWidth().padding(13.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        lineHeight = 15.sp,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("完成") }
        },
    )
}

@Composable
private fun PreviewScenarioSelector(
    selected: StudioPreviewScenario,
    onSelect: (StudioPreviewScenario) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        StudioPreviewScenario.entries.forEach { scenario ->
            Surface(
                onClick = { onSelect(scenario) },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(15.dp),
                color = if (scenario == selected) {
                    MaterialTheme.colorScheme.primary
                } else {
                    MaterialTheme.colorScheme.surfaceContainer
                },
                contentColor = if (scenario == selected) {
                    MaterialTheme.colorScheme.onPrimary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
            ) {
                Text(
                    scenario.label,
                    modifier = Modifier.padding(vertical = 9.dp),
                    textAlign = TextAlign.Center,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Black,
                )
            }
        }
    }
}

@Composable
private fun PreviewReferenceCard(style: UiStyle, scenario: StudioPreviewScenario) {
    val tokens = LocalMiuixTokens.current
    PreviewPanel(
        title = "A · 当前系统字体",
        subtitle = "作为视觉比例和基线参考",
        style = style,
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 18.dp),
            color = if (style == UiStyle.MIUIX) tokens.textPrimary.copy(alpha = .035f)
            else MaterialTheme.colorScheme.surfaceContainer,
        ) {
            SystemScenarioPreview(scenario)
        }
    }
}

@Composable
private fun PreviewCandidateCard(
    style: UiStyle,
    state: FontStudioUiState,
    scenario: StudioPreviewScenario,
) {
    PreviewPanel(
        title = "B · 当前组合方案",
        subtitle = "中文、英文和数字分别使用所选槽位",
        style = style,
    ) {
        val missing = state.slots.count { it.font == null }
        if (missing > 0) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.errorContainer,
            ) {
                Text(
                    "还有 $missing 个槽位未选择字体，选择完成后即可预览。",
                    modifier = Modifier.padding(13.dp),
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    fontSize = 11.sp,
                )
            }
        } else {
            CandidateScenarioPreview(state, scenario)
        }
    }
}

@Composable
private fun PreviewPanel(
    title: String,
    subtitle: String,
    style: UiStyle,
    content: @Composable () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 28.dp else 23.dp),
        color = if (style == UiStyle.MIUIX) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow,
        shadowElevation = if (style == UiStyle.MIUIX) 5.dp else 0.dp,
    ) {
        Column(Modifier.padding(15.dp)) {
            Text(title, fontSize = 13.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
            Spacer(Modifier.height(10.dp))
            content()
        }
    }
}

@Composable
private fun SystemScenarioPreview(scenario: StudioPreviewScenario) {
    Column(Modifier.fillMaxWidth().padding(horizontal = 15.dp, vertical = 14.dp)) {
        when (scenario) {
            StudioPreviewScenario.MIXED -> PreviewGuideBox {
                Text("洛书 LuoShu 2026 · 字体组合", fontSize = 24.sp, fontWeight = FontWeight.Medium)
            }
            StudioPreviewScenario.BODY -> {
                Text("字体不仅影响外观，也影响阅读节奏与信息层级。", fontSize = 17.sp, lineHeight = 25.sp)
                Text("Typography shapes rhythm and hierarchy.", fontSize = 14.sp)
                Text("2026-07-24  19:30", fontSize = 14.sp, fontWeight = FontWeight.Medium)
            }
            StudioPreviewScenario.INTERFACE -> {
                Text("字体设置", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                Text("System typography and fallback", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                Spacer(Modifier.height(7.dp))
                Text("已验证 · 3 个字体槽位", fontSize = 14.sp, fontWeight = FontWeight.Medium)
            }
            StudioPreviewScenario.NUMBERS -> {
                Text("本月用量", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                Text("¥ 12,680.50", fontSize = 31.sp, fontWeight = FontWeight.Bold)
                Text("+18.6%  ·  19:30", fontSize = 14.sp, fontWeight = FontWeight.Medium)
            }
        }
    }
}

@Composable
private fun CandidateScenarioPreview(state: FontStudioUiState, scenario: StudioPreviewScenario) {
    val cjk = state.slots.first { it.slot == MixSlot.Cjk }
    val latin = state.slots.first { it.slot == MixSlot.Latin }
    val digit = state.slots.first { it.slot == MixSlot.Digit }
    val panelColor = MaterialTheme.colorScheme.surfaceContainer

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = panelColor,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 12.dp)) {
            when (scenario) {
                StudioPreviewScenario.MIXED -> PreviewGuideBox {
                    Row(
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        NativeFontPreview(
                            font = cjk.font,
                            text = "洛书",
                            axes = cjk.axes,
                            modifier = Modifier.weight(.27f).height(44.dp),
                            textSizeSp = 23f,
                            gravity = Gravity.END or Gravity.CENTER_VERTICAL,
                            maxLines = 1,
                        )
                        NativeFontPreview(
                            font = latin.font,
                            text = " LuoShu ",
                            axes = latin.axes,
                            modifier = Modifier.weight(.45f).height(44.dp),
                            textSizeSp = 23f,
                            gravity = Gravity.CENTER,
                            maxLines = 1,
                        )
                        NativeFontPreview(
                            font = digit.font,
                            text = "2026",
                            axes = digit.axes,
                            modifier = Modifier.weight(.28f).height(44.dp),
                            textSizeSp = 23f,
                            gravity = Gravity.START or Gravity.CENTER_VERTICAL,
                            maxLines = 1,
                        )
                    }
                }
                StudioPreviewScenario.BODY -> {
                    NativeFontPreview(cjk.font, "字体不仅影响外观，也影响阅读节奏与信息层级。", cjk.axes, Modifier.fillMaxWidth().height(38.dp), 17f, maxLines = 1)
                    NativeFontPreview(latin.font, "Typography shapes rhythm and hierarchy.", latin.axes, Modifier.fillMaxWidth().height(32.dp), 14f, maxLines = 1)
                    NativeFontPreview(digit.font, "2026-07-24  19:30", digit.axes, Modifier.fillMaxWidth().height(32.dp), 14f, maxLines = 1)
                }
                StudioPreviewScenario.INTERFACE -> {
                    NativeFontPreview(cjk.font, "字体设置", cjk.axes, Modifier.fillMaxWidth().height(39.dp), 21f, maxLines = 1)
                    NativeFontPreview(latin.font, "System typography and fallback", latin.axes, Modifier.fillMaxWidth().height(28.dp), 12f, maxLines = 1)
                    Spacer(Modifier.height(4.dp))
                    Row(Modifier.fillMaxWidth().height(34.dp), verticalAlignment = Alignment.CenterVertically) {
                        NativeFontPreview(cjk.font, "已验证 · ", cjk.axes, Modifier.weight(.48f).height(32.dp), 14f, Gravity.END or Gravity.CENTER_VERTICAL, 1)
                        NativeFontPreview(digit.font, "3", digit.axes, Modifier.width(25.dp).height(32.dp), 14f, Gravity.CENTER, 1)
                        NativeFontPreview(cjk.font, " 个字体槽位", cjk.axes, Modifier.weight(.52f).height(32.dp), 14f, Gravity.START or Gravity.CENTER_VERTICAL, 1)
                    }
                }
                StudioPreviewScenario.NUMBERS -> {
                    NativeFontPreview(cjk.font, "本月用量", cjk.axes, Modifier.fillMaxWidth().height(28.dp), 12f, maxLines = 1)
                    NativeFontPreview(digit.font, "¥ 12,680.50", digit.axes, Modifier.fillMaxWidth().height(50.dp), 31f, maxLines = 1)
                    Row(Modifier.fillMaxWidth().height(32.dp), verticalAlignment = Alignment.CenterVertically) {
                        NativeFontPreview(digit.font, "+18.6%", digit.axes, Modifier.weight(1f).height(30.dp), 14f, Gravity.END or Gravity.CENTER_VERTICAL, 1)
                        NativeFontPreview(latin.font, " · ", latin.axes, Modifier.width(26.dp).height(30.dp), 14f, Gravity.CENTER, 1)
                        NativeFontPreview(digit.font, "19:30", digit.axes, Modifier.weight(1f).height(30.dp), 14f, Gravity.START or Gravity.CENTER_VERTICAL, 1)
                    }
                }
            }
        }
    }
}

@Composable
private fun PreviewGuideBox(content: @Composable () -> Unit) {
    val lineColor = MaterialTheme.colorScheme.primary.copy(alpha = .26f)
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(52.dp)
            .drawBehind {
                val y = size.height * .72f
                drawLine(
                    color = lineColor,
                    start = androidx.compose.ui.geometry.Offset(0f, y),
                    end = androidx.compose.ui.geometry.Offset(size.width, y),
                    strokeWidth = 1.dp.toPx(),
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        content()
    }
}

@Composable
private fun QuickPresetGrid(
    style: UiStyle,
    enabled: Boolean,
    onApplyPreset: (StudioQuickPreset) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        studioQuickPresets.chunked(2).forEach { rowPresets ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                rowPresets.forEach { preset ->
                    Surface(
                        onClick = { onApplyPreset(preset) },
                        enabled = enabled,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 20.dp else 17.dp),
                        color = MaterialTheme.colorScheme.surfaceContainer,
                    ) {
                        Column(Modifier.padding(horizontal = 12.dp, vertical = 11.dp)) {
                            Text(preset.label, fontSize = 12.sp, fontWeight = FontWeight.Black)
                            Text(
                                preset.description,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 9.sp,
                                lineHeight = 12.sp,
                            )
                            Spacer(Modifier.height(5.dp))
                            Text(
                                "${preset.cjkWeight} · ${preset.latinWeight} · ${preset.digitWeight}",
                                color = MaterialTheme.colorScheme.primary,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
                if (rowPresets.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}
