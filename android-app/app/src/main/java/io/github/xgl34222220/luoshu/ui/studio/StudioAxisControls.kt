package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.rememberWeightAxisInfo
import io.github.xgl34222220.luoshu.ui.font.fontAxisDisplayName
import io.github.xgl34222220.luoshu.ui.font.fontAxisValueLabel
import io.github.xgl34222220.luoshu.ui.font.fontFixedWeight
import io.github.xgl34222220.luoshu.ui.font.fontStaticWeights
import io.github.xgl34222220.luoshu.ui.font.fontWeightName
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import kotlin.math.roundToInt

@Composable
internal fun MaterialStudioAxisControls(
    font: FontItem,
    weight: Int,
    axes: Map<String, Float>,
    enabled: Boolean,
    onWeight: (Int) -> Unit,
    onAxis: (String, Float) -> Unit,
) {
    val axisInfo = rememberWeightAxisInfo(font)
    when {
        font.variable && axisInfo.loading -> AxisLoadingRow()
        font.variable && axisInfo.axes.isNotEmpty() -> {
            Column(verticalArrangement = Arrangement.spacedBy(13.dp)) {
                axisInfo.axes.forEach { axis ->
                    val minimum = axis.min
                    val maximum = axis.max.coerceAtLeast(minimum)
                    val isWeight = axis.tag == "wght"
                    val current = (axes[axis.tag] ?: if (isWeight) weight.toFloat() else axis.default)
                        .coerceIn(minimum, maximum)
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(fontAxisDisplayName(axis.tag), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                Text(axis.tag, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                            }
                            Surface(
                                shape = RoundedCornerShape(999.dp),
                                color = MaterialTheme.colorScheme.primaryContainer,
                            ) {
                                Text(
                                    fontAxisValueLabel(current),
                                    modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
                                    color = MaterialTheme.colorScheme.primary,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.SemiBold,
                                )
                            }
                        }
                        Slider(
                            value = current,
                            onValueChange = { raw ->
                                val next = if (isWeight) {
                                    ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum)
                                } else raw.coerceIn(minimum, maximum)
                                onAxis(axis.tag, next)
                            },
                            enabled = enabled && maximum > minimum,
                            valueRange = minimum..maximum,
                            steps = if (isWeight && maximum > minimum) {
                                (((maximum - minimum) / 10f).roundToInt() - 1).coerceAtLeast(0)
                            } else 0,
                        )
                        Text(
                            "${fontAxisValueLabel(minimum)} · 默认 ${fontAxisValueLabel(axis.default)} · ${fontAxisValueLabel(maximum)}",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 12.sp,
                        )
                    }
                }
            }
        }
        fontStaticWeights(font).size >= 2 -> {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).selectableGroup(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                fontStaticWeights(font).forEach { option ->
                    MaterialWeightChip(
                        text = fontWeightName(option),
                        selected = option == weight,
                        enabled = enabled,
                        onClick = { onWeight(option) },
                    )
                }
            }
        }
        else -> {
            Text(
                "字重：${fontWeightName(fontFixedWeight(font))}，此字体不支持调节。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
internal fun MiuixStudioAxisControls(
    font: FontItem,
    weight: Int,
    axes: Map<String, Float>,
    enabled: Boolean,
    onWeight: (Int) -> Unit,
    onAxis: (String, Float) -> Unit,
) {
    val axisInfo = rememberWeightAxisInfo(font)
    val tokens = LocalMiuixTokens.current
    when {
        font.variable && axisInfo.loading -> AxisLoadingRow()
        font.variable && axisInfo.axes.isNotEmpty() -> {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                axisInfo.axes.forEach { axis ->
                    val minimum = axis.min
                    val maximum = axis.max.coerceAtLeast(minimum)
                    val isWeight = axis.tag == "wght"
                    val current = (axes[axis.tag] ?: if (isWeight) weight.toFloat() else axis.default)
                        .coerceIn(minimum, maximum)
                    Surface(
                        shape = RoundedCornerShape(22.dp),
                        color = tokens.textPrimary.copy(alpha = .035f),
                    ) {
                        Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    fontAxisDisplayName(axis.tag),
                                    color = tokens.textPrimary,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.weight(1f),
                                )
                                Text(axis.tag, color = tokens.textSecondary, fontSize = 12.sp)
                                Spacer(Modifier.width(8.dp))
                                Surface(
                                    shape = RoundedCornerShape(999.dp),
                                    color = MaterialTheme.colorScheme.primary.copy(alpha = .12f),
                                ) {
                                    Text(
                                        fontAxisValueLabel(current),
                                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                                        color = MaterialTheme.colorScheme.primary,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.SemiBold,
                                    )
                                }
                            }
                            Slider(
                                value = current,
                                onValueChange = { raw ->
                                    val next = if (isWeight) {
                                        ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum)
                                    } else raw.coerceIn(minimum, maximum)
                                    onAxis(axis.tag, next)
                                },
                                enabled = enabled && maximum > minimum,
                                valueRange = minimum..maximum,
                                steps = if (isWeight && maximum > minimum) {
                                    (((maximum - minimum) / 10f).roundToInt() - 1).coerceAtLeast(0)
                                } else 0,
                            )
                            Row(Modifier.fillMaxWidth()) {
                                Text(fontAxisValueLabel(minimum), color = tokens.textSecondary, fontSize = 12.sp)
                                Spacer(Modifier.weight(1f))
                                Text("默认 ${fontAxisValueLabel(axis.default)}", color = tokens.textSecondary, fontSize = 12.sp)
                                Spacer(Modifier.weight(1f))
                                Text(fontAxisValueLabel(maximum), color = tokens.textSecondary, fontSize = 12.sp)
                            }
                        }
                    }
                }
            }
        }
        fontStaticWeights(font).size >= 2 -> {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).selectableGroup(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                fontStaticWeights(font).forEach { option ->
                    MiuixWeightChip(
                        text = fontWeightName(option),
                        selected = option == weight,
                        enabled = enabled,
                        onClick = { onWeight(option) },
                    )
                }
            }
        }
        else -> {
            Surface(
                shape = RoundedCornerShape(18.dp),
                color = tokens.textPrimary.copy(alpha = .035f),
            ) {
                Text(
                    "字重：${fontWeightName(fontFixedWeight(font))} · 无需调节",
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 10.dp),
                    color = tokens.textSecondary,
                    fontSize = 12.sp,
                )
            }
        }
    }
}

@Composable
private fun AxisLoadingRow() {
    Row(verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
        Spacer(Modifier.width(9.dp))
        Text("正在读取可调参数…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
    }
}

@Composable
private fun MaterialWeightChip(text: String, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    WeightChoiceChip(text, selected, enabled, RoundedCornerShape(999.dp), onClick)
}

@Composable
private fun MiuixWeightChip(text: String, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    WeightChoiceChip(text, selected, enabled, RoundedCornerShape(16.dp), onClick)
}

@Composable
private fun WeightChoiceChip(
    text: String,
    selected: Boolean,
    enabled: Boolean,
    shape: RoundedCornerShape,
    onClick: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    Surface(
        modifier = Modifier.clip(shape).selectable(
            selected = selected,
            enabled = enabled,
            role = Role.RadioButton,
            onClick = onClick,
        ),
        shape = shape,
        color = if (selected) scheme.primary else scheme.surfaceContainerHigh,
        contentColor = (if (selected) scheme.onPrimary else scheme.onSurface)
            .copy(alpha = if (enabled) 1f else .45f),
    ) {
        Box(
            Modifier.heightIn(min = 48.dp).padding(horizontal = 14.dp, vertical = 10.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(text, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}
