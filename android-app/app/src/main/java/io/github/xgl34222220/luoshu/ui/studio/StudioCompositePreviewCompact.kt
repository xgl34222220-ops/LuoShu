package io.github.xgl34222220.luoshu.ui.studio

import android.view.Gravity
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

private enum class CompactPreviewScenario(val label: String) {
    MIXED("混排"), BODY("正文"), INTERFACE("界面"), WECHAT("微信"), PLAY("Play"), STATUS("状态栏"),
    NUMBERS("金额"), SMALL("小字"), HEADLINE("标题"),
}

@Composable
internal fun StudioCompositePreviewDialogCompact(
    style: UiStyle,
    state: FontStudioUiState,
    onApplyPreset: (StudioQuickPreset) -> Unit,
    onDismiss: () -> Unit,
) {
    var scenarioName by rememberSaveable { mutableStateOf(CompactPreviewScenario.MIXED.name) }
    val scenario = remember(scenarioName) {
        CompactPreviewScenario.entries.firstOrNull { it.name == scenarioName } ?: CompactPreviewScenario.MIXED
    }
    val tokens = LocalMiuixTokens.current
    val miuix = style == UiStyle.MIUIX

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 28.dp)
                .heightIn(max = 820.dp),
            shape = RoundedCornerShape(if (miuix) 36.dp else 30.dp),
            color = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh,
            shadowElevation = 18.dp,
        ) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("最终组合预览", fontSize = 25.sp, fontWeight = FontWeight.Black)
                        Text(
                            "对照系统字体，检查混排比例、字重和基线",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 11.sp,
                        )
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Rounded.Close, contentDescription = "关闭")
                    }
                }

                Spacer(Modifier.height(12.dp))
                CompactScenarioSelector(
                    selected = scenario,
                    onSelect = { scenarioName = it.name },
                )

                LazyColumn(
                    modifier = Modifier.weight(1f, fill = false),
                    contentPadding = PaddingValues(top = 12.dp, bottom = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    item {
                        CompactPreviewCard(
                            title = "A · 当前系统字体",
                            subtitle = "作为视觉比例和基线参考",
                            style = style,
                        ) {
                            SystemPreviewCompact(scenario)
                        }
                    }
                    item {
                        CompactPreviewCard(
                            title = "B · 当前组合方案",
                            subtitle = "中文、英文和数字分别使用所选槽位",
                            style = style,
                        ) {
                            CandidatePreviewCompact(state, scenario)
                        }
                    }
                    item {
                        Column(Modifier.padding(top = 2.dp)) {
                            Text("快速方案", fontSize = 17.sp, fontWeight = FontWeight.Black)
                            Text(
                                "只调整三个槽位的字重，不会更换已选择字体。",
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 10.sp,
                            )
                        }
                    }
                    items(studioQuickPresets, key = { it.id }) { preset ->
                        CompactPresetRow(
                            preset = preset,
                            enabled = !state.busy && !state.operationBusy,
                            onClick = { onApplyPreset(preset) },
                        )
                    }
                    item {
                        Surface(
                            shape = RoundedCornerShape(18.dp),
                            color = MaterialTheme.colorScheme.primary.copy(alpha = .08f),
                        ) {
                            Text(
                                "这是槽位级视觉模拟。最终覆盖率、系统加载和开机结果仍以生成任务与设备验证为准。",
                                modifier = Modifier.fillMaxWidth().padding(13.dp),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 10.sp,
                                lineHeight = 15.sp,
                            )
                        }
                    }
                }

                Button(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    shape = RoundedCornerShape(19.dp),
                ) {
                    Icon(Icons.Rounded.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(7.dp))
                    Text("完成", fontWeight = FontWeight.Black)
                }
            }
        }
    }
}

@Composable
private fun CompactScenarioSelector(
    selected: CompactPreviewScenario,
    onSelect: (CompactPreviewScenario) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        CompactPreviewScenario.entries.forEach { scenario ->
            Surface(
                onClick = { onSelect(scenario) },
                modifier = Modifier.width(66.dp),
                shape = RoundedCornerShape(15.dp),
                color = if (scenario == selected) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.surfaceContainer,
                contentColor = if (scenario == selected) MaterialTheme.colorScheme.onPrimary
                else MaterialTheme.colorScheme.onSurfaceVariant,
            ) {
                Text(
                    scenario.label,
                    modifier = Modifier.padding(vertical = 10.dp),
                    textAlign = TextAlign.Center,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Black,
                )
            }
        }
    }
}

@Composable
private fun CompactPreviewCard(
    title: String,
    subtitle: String,
    style: UiStyle,
    content: @Composable () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 27.dp else 22.dp),
        color = if (style == UiStyle.MIUIX) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow,
        shadowElevation = if (style == UiStyle.MIUIX) 4.dp else 0.dp,
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontSize = 14.sp, fontWeight = FontWeight.Black)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
            Spacer(Modifier.height(9.dp))
            content()
        }
    }
}

@Composable
private fun SystemPreviewCompact(scenario: CompactPreviewScenario) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(19.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 13.dp)) {
            when (scenario) {
                CompactPreviewScenario.MIXED -> Text(
                    "洛书 LuoShu 2026",
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                CompactPreviewScenario.BODY -> {
                    Text("字体影响阅读节奏与信息层级。", fontSize = 16.sp)
                    Text("Typography shapes rhythm.", fontSize = 13.sp)
                    Text("2026-07-24  19:30", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                }
                CompactPreviewScenario.INTERFACE -> {
                    Text("字体设置", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text("System typography and fallback", fontSize = 12.sp)
                    Text("已验证 · 3 个字体槽位", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                }
                CompactPreviewScenario.WECHAT -> {
                    Text("公众号文章标题", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text("正文排版：中文阅读与 English 混排 2026", fontSize = 14.sp, lineHeight = 20.sp)
                }
                CompactPreviewScenario.PLAY -> {
                    Text("Google Play", fontSize = 19.sp, fontWeight = FontWeight.Bold)
                    Text("应用与游戏 · Apps & games", fontSize = 13.sp)
                    Text("4.8 ★  ·  12 MB", fontSize = 12.sp)
                }
                CompactPreviewScenario.STATUS -> {
                    Text("09:41   5G   88%", fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text("状态栏数字、符号与紧凑字宽", fontSize = 11.sp)
                }
                CompactPreviewScenario.SMALL -> {
                    Text("辅助说明 · Secondary text · 12:45", fontSize = 10.sp)
                    Text("小字号仍应保持清晰、字腔不过度拥挤。", fontSize = 11.sp)
                }
                CompactPreviewScenario.HEADLINE -> {
                    Text("洛书字体引擎", fontSize = 27.sp, fontWeight = FontWeight.Black)
                    Text("LuoShu Typography 2026", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                }
                CompactPreviewScenario.NUMBERS -> {
                    Text("本月用量", fontSize = 12.sp)
                    Text("¥ 12,680.50", fontSize = 28.sp, fontWeight = FontWeight.Bold)
                    Text("+18.6% · 19:30", fontSize = 13.sp, fontWeight = FontWeight.Medium)
                }
            }
        }
    }
}

@Composable
private fun CandidatePreviewCompact(state: FontStudioUiState, scenario: CompactPreviewScenario) {
    val cjk = state.slots.firstOrNull { it.slot == MixSlot.Cjk }
    val latin = state.slots.firstOrNull { it.slot == MixSlot.Latin }
    val digit = state.slots.firstOrNull { it.slot == MixSlot.Digit }
    val missing = listOf(cjk, latin, digit).count { it?.font == null }

    if (missing > 0 || cjk == null || latin == null || digit == null) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(18.dp),
            color = MaterialTheme.colorScheme.errorContainer,
        ) {
            Text(
                "还有 $missing 个槽位未选择字体。",
                modifier = Modifier.padding(13.dp),
                color = MaterialTheme.colorScheme.onErrorContainer,
                fontSize = 11.sp,
            )
        }
        return
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(19.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 11.dp)) {
            when (scenario) {
                CompactPreviewScenario.MIXED -> Row(
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    NativeFontPreview(cjk.font, "洛书", cjk.axes, Modifier.weight(.28f).height(44.dp), 20f, Gravity.END or Gravity.CENTER_VERTICAL, 1)
                    NativeFontPreview(latin.font, " LuoShu ", latin.axes, Modifier.weight(.42f).height(44.dp), 20f, Gravity.CENTER, 1)
                    NativeFontPreview(digit.font, "2026", digit.axes, Modifier.weight(.30f).height(44.dp), 19f, Gravity.START or Gravity.CENTER_VERTICAL, 1)
                }
                CompactPreviewScenario.BODY -> {
                    NativeFontPreview(cjk.font, "字体影响阅读节奏与信息层级。", cjk.axes, Modifier.fillMaxWidth().height(34.dp), 16f, maxLines = 1)
                    NativeFontPreview(latin.font, "Typography shapes rhythm.", latin.axes, Modifier.fillMaxWidth().height(29.dp), 13f, maxLines = 1)
                    NativeFontPreview(digit.font, "2026-07-24  19:30", digit.axes, Modifier.fillMaxWidth().height(29.dp), 13f, maxLines = 1)
                }
                CompactPreviewScenario.INTERFACE -> {
                    NativeFontPreview(cjk.font, "字体设置", cjk.axes, Modifier.fillMaxWidth().height(37.dp), 20f, maxLines = 1)
                    NativeFontPreview(latin.font, "System typography and fallback", latin.axes, Modifier.fillMaxWidth().height(27.dp), 12f, maxLines = 1)
                    NativeFontPreview(cjk.font, "已验证 · 3 个字体槽位", cjk.axes, Modifier.fillMaxWidth().height(30.dp), 13f, maxLines = 1)
                }
                CompactPreviewScenario.WECHAT -> {
                    NativeFontPreview(cjk.font, "公众号文章标题", cjk.axes, Modifier.fillMaxWidth().height(38.dp), 20f, maxLines = 1)
                    NativeFontPreview(cjk.font, "正文排版：中文阅读与", cjk.axes, Modifier.fillMaxWidth().height(29.dp), 14f, maxLines = 1)
                    NativeFontPreview(latin.font, "English 2026", latin.axes, Modifier.fillMaxWidth().height(29.dp), 14f, maxLines = 1)
                }
                CompactPreviewScenario.PLAY -> {
                    NativeFontPreview(latin.font, "Google Play", latin.axes, Modifier.fillMaxWidth().height(36.dp), 19f, maxLines = 1)
                    NativeFontPreview(cjk.font, "应用与游戏", cjk.axes, Modifier.fillMaxWidth().height(28.dp), 13f, maxLines = 1)
                    NativeFontPreview(digit.font, "4.8 ★ · 12 MB", digit.axes, Modifier.fillMaxWidth().height(28.dp), 12f, maxLines = 1)
                }
                CompactPreviewScenario.STATUS -> {
                    NativeFontPreview(digit.font, "09:41   5G   88%", digit.axes, Modifier.fillMaxWidth().height(34.dp), 15f, maxLines = 1)
                    NativeFontPreview(cjk.font, "状态栏数字、符号与紧凑字宽", cjk.axes, Modifier.fillMaxWidth().height(26.dp), 11f, maxLines = 1)
                }
                CompactPreviewScenario.SMALL -> {
                    NativeFontPreview(latin.font, "Secondary text · 12:45", latin.axes, Modifier.fillMaxWidth().height(25.dp), 10f, maxLines = 1)
                    NativeFontPreview(cjk.font, "小字号仍应保持清晰、字腔不过度拥挤。", cjk.axes, Modifier.fillMaxWidth().height(26.dp), 11f, maxLines = 1)
                }
                CompactPreviewScenario.HEADLINE -> {
                    NativeFontPreview(cjk.font, "洛书字体引擎", cjk.axes, Modifier.fillMaxWidth().height(48.dp), 27f, maxLines = 1)
                    NativeFontPreview(latin.font, "LuoShu Typography 2026", latin.axes, Modifier.fillMaxWidth().height(34.dp), 16f, maxLines = 1)
                }
                CompactPreviewScenario.NUMBERS -> {
                    NativeFontPreview(cjk.font, "本月用量", cjk.axes, Modifier.fillMaxWidth().height(27.dp), 12f, maxLines = 1)
                    NativeFontPreview(digit.font, "¥ 12,680.50", digit.axes, Modifier.fillMaxWidth().height(47.dp), 28f, maxLines = 1)
                    NativeFontPreview(digit.font, "+18.6% · 19:30", digit.axes, Modifier.fillMaxWidth().height(30.dp), 13f, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun CompactPresetRow(
    preset: StudioQuickPreset,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(19.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(38.dp),
                shape = RoundedCornerShape(14.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Rounded.Tune, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(19.dp))
                }
            }
            Spacer(Modifier.width(11.dp))
            Column(Modifier.weight(1f)) {
                Text(preset.label, fontSize = 13.sp, fontWeight = FontWeight.Black)
                Text(
                    preset.description,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 9.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Text(
                "${preset.cjkWeight} · ${preset.latinWeight} · ${preset.digitWeight}",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}
