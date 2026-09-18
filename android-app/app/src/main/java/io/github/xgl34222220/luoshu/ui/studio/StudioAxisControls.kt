package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsDraggedAsState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
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
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLoadingSkeleton
import kotlin.math.abs
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
                    val sliderInteraction = remember(font.id, axis.tag) { MutableInteractionSource() }
                    val dragging by sliderInteraction.collectIsDraggedAsState()
                    val badgeScale by animateFloatAsState(
                        targetValue = if (dragging) 1.05f else 1f,
                        animationSpec = spring(dampingRatio = .72f, stiffness = Spring.StiffnessMedium),
                        label = "axisValueBadge",
                    )
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(fontAxisDisplayName(axis.tag), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                Text(axis.tag, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 12.sp)
                            }
                            Surface(
                                modifier = Modifier.graphicsLayer {
                                    scaleX = badgeScale
                                    scaleY = badgeScale
                                    translationY = if (dragging) -2.dp.toPx() else 0f
                                },
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
                        InteractiveAxisSlider(
                            key = "${font.id}:${axis.tag}",
                            current = current,
                            minimum = minimum,
                            maximum = maximum,
                            isWeight = isWeight,
                            enabled = enabled,
                            interactionSource = sliderInteraction,
                            dragging = dragging,
                            onValueChange = { onAxis(axis.tag, it) },
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
                    val sliderInteraction = remember(font.id, axis.tag) { MutableInteractionSource() }
                    val dragging by sliderInteraction.collectIsDraggedAsState()
                    val badgeScale by animateFloatAsState(
                        targetValue = if (dragging) 1.05f else 1f,
                        animationSpec = spring(dampingRatio = .72f, stiffness = Spring.StiffnessMedium),
                        label = "axisValueBadge",
                    )
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
                                    modifier = Modifier.graphicsLayer {
                                        scaleX = badgeScale
                                        scaleY = badgeScale
                                        translationY = if (dragging) -2.dp.toPx() else 0f
                                    },
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
                            InteractiveAxisSlider(
                                key = "${font.id}:${axis.tag}",
                                current = current,
                                minimum = minimum,
                                maximum = maximum,
                                isWeight = isWeight,
                                enabled = enabled,
                                interactionSource = sliderInteraction,
                                dragging = dragging,
                                onValueChange = { onAxis(axis.tag, it) },
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
private fun InteractiveAxisSlider(
    key: String,
    current: Float,
    minimum: Float,
    maximum: Float,
    isWeight: Boolean,
    enabled: Boolean,
    interactionSource: MutableInteractionSource,
    dragging: Boolean,
    onValueChange: (Float) -> Unit,
) {
    val haptic = LocalHapticFeedback.current
    var lastHapticWeight by remember(key) { mutableStateOf<Int?>(null) }
    val range = (maximum - minimum).coerceAtLeast(.0001f)
    val fraction = ((current - minimum) / range).coerceIn(0f, 1f)
    val scheme = MaterialTheme.colorScheme

    BoxWithConstraints(
        modifier = Modifier.fillMaxWidth().height(72.dp),
    ) {
        val bubbleWidth = 54.dp
        val haloSize = 32.dp
        val bubbleX = (maxWidth - bubbleWidth) * fraction
        val haloX = (maxWidth - haloSize) * fraction

        if (dragging) {
            Box(
                modifier = Modifier
                    .offset(x = haloX, y = 32.dp)
                    .size(haloSize)
                    .background(scheme.primary.copy(alpha = .14f), CircleShape),
            )
        }

        Slider(
            value = current,
            onValueChange = { raw ->
                val magnetic = if (isWeight) standardWeightSnap(raw, minimum, maximum) else null
                val next = when {
                    magnetic != null -> magnetic.toFloat()
                    isWeight -> ((raw / 10f).roundToInt() * 10).toFloat().coerceIn(minimum, maximum)
                    else -> raw.coerceIn(minimum, maximum)
                }
                if (magnetic != null && lastHapticWeight != magnetic) {
                    haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                    lastHapticWeight = magnetic
                } else if (magnetic == null && lastHapticWeight != null &&
                    abs(raw - lastHapticWeight!!.toFloat()) > 22f
                ) {
                    lastHapticWeight = null
                }
                onValueChange(next)
            },
            modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
            interactionSource = interactionSource,
            enabled = enabled && maximum > minimum,
            valueRange = minimum..maximum,
            steps = if (isWeight && maximum > minimum) {
                (((maximum - minimum) / 10f).roundToInt() - 1).coerceAtLeast(0)
            } else 0,
        )

        AnimatedVisibility(
            visible = dragging,
            modifier = Modifier.offset(x = bubbleX),
            enter = fadeIn(tween(90)),
            exit = fadeOut(tween(90)),
        ) {
            Surface(
                modifier = Modifier.width(bubbleWidth),
                shape = RoundedCornerShape(14.dp),
                color = scheme.primary,
                contentColor = scheme.onPrimary,
                shadowElevation = 5.dp,
            ) {
                Text(
                    fontAxisValueLabel(current),
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                )
            }
        }
    }
}

@Composable
private fun AxisLoadingRow() {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        LuoShuLoadingSkeleton(Modifier.fillMaxWidth(.36f).height(14.dp))
        LuoShuLoadingSkeleton(
            Modifier.fillMaxWidth().height(42.dp),
            shape = RoundedCornerShape(18.dp),
        )
    }
}

private fun standardWeightSnap(raw: Float, minimum: Float, maximum: Float): Int? =
    listOf(300, 400, 500, 600, 700, 900).firstOrNull { target ->
        target.toFloat() in minimum..maximum && abs(raw - target.toFloat()) <= 12f
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
