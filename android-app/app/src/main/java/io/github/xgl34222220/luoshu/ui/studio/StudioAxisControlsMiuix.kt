package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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
import kotlin.math.roundToInt
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.CircularProgressIndicator
import top.yukonga.miuix.kmp.basic.Slider
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.basic.TextButton
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun StudioAxisControlsMiuix(
    font: FontItem,
    weight: Int,
    axes: Map<String, Float>,
    enabled: Boolean,
    onWeight: (Int) -> Unit,
    onAxis: (String, Float) -> Unit,
) {
    val axisInfo = rememberWeightAxisInfo(font)
    val colors = MiuixTheme.colorScheme

    when {
        font.variable && axisInfo.loading -> {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(
                    progress = null,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(9.dp))
                Text(
                    text = "正在读取真实可变轴…",
                    color = colors.onSurfaceSecondary,
                )
            }
        }
        font.variable && axisInfo.axes.isNotEmpty() -> {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                axisInfo.axes.forEach { axis ->
                    val minimum = axis.min
                    val maximum = axis.max.coerceAtLeast(minimum)
                    val isWeight = axis.tag == "wght"
                    val current = (axes[axis.tag] ?: if (isWeight) weight.toFloat() else axis.default)
                        .coerceIn(minimum, maximum)

                    Card(modifier = Modifier.fillMaxWidth()) {
                        BasicComponent(
                            title = fontAxisDisplayName(axis.tag),
                            summary = "${axis.tag} · ${fontAxisValueLabel(current)}",
                        )
                        Column(Modifier.padding(horizontal = 16.dp, vertical = 10.dp)) {
                            Slider(
                                value = current,
                                onValueChange = { raw ->
                                    val next = if (isWeight) {
                                        ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum)
                                    } else {
                                        raw.coerceIn(minimum, maximum)
                                    }
                                    onAxis(axis.tag, next)
                                },
                                enabled = enabled,
                                valueRange = minimum..maximum,
                            )
                            Row(Modifier.fillMaxWidth()) {
                                Text(
                                    text = fontAxisValueLabel(minimum),
                                    color = colors.onSurfaceSecondary,
                                    fontSize = 10.sp,
                                )
                                Spacer(Modifier.weight(1f))
                                Text(
                                    text = "默认 ${fontAxisValueLabel(axis.default)}",
                                    color = colors.primary,
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold,
                                )
                                Spacer(Modifier.weight(1f))
                                Text(
                                    text = fontAxisValueLabel(maximum),
                                    color = colors.onSurfaceSecondary,
                                    fontSize = 10.sp,
                                )
                            }
                        }
                    }
                }
            }
        }
        fontStaticWeights(font).size >= 2 -> {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                fontStaticWeights(font).forEach { option ->
                    if (option == weight) {
                        Button(
                            onClick = { onWeight(option) },
                            enabled = enabled,
                        ) {
                            Text(fontWeightName(option), fontWeight = FontWeight.Bold)
                        }
                    } else {
                        TextButton(
                            text = fontWeightName(option),
                            enabled = enabled,
                            onClick = { onWeight(option) },
                        )
                    }
                }
            }
        }
        else -> {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "固定字重",
                    summary = "${fontWeightName(fontFixedWeight(font))} · 没有可调设计轴",
                )
            }
        }
    }
}
