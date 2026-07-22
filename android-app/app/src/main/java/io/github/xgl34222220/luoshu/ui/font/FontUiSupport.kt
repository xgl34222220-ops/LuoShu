package io.github.xgl34222220.luoshu.ui.font

import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.MixState
import kotlin.math.abs
import kotlin.math.roundToInt

internal fun fontStaticWeights(font: FontItem): List<Int> = font.weights
    .filterNot { it.equals("variable", ignoreCase = true) }
    .map(::fontRoleWeight)
    .distinct()
    .sorted()

internal fun fontFixedWeight(font: FontItem): Int = fontStaticWeights(font).firstOrNull() ?: 400

internal fun fontNormalizedWeight(font: FontItem, current: Int): Int =
    cachedFontDefaultWeight(font.id) ?: when {
        font.variable -> 400
        400 in fontStaticWeights(font) -> 400
        fontStaticWeights(font).size >= 2 -> fontStaticWeights(font).minByOrNull { abs(it - 400) } ?: 400
        else -> fontFixedWeight(font)
    }

internal fun fontPreviewWeight(font: FontItem): Int {
    val weights = fontStaticWeights(font)
    return when {
        font.variable -> 400
        400 in weights -> 400
        500 in weights -> 500
        weights.isEmpty() -> 400
        else -> weights.minWithOrNull(
            compareBy<Int> { abs(it - 500) }.thenByDescending { it },
        ) ?: 400
    }
}

internal fun fontCapabilityLabel(font: FontItem): String {
    val capability = when {
        font.variable -> "可变字体"
        fontStaticWeights(font).size >= 2 ->
            "多字重 · ${fontStaticWeights(font).joinToString(" / ")}"
        else -> "固定 ${fontWeightName(fontFixedWeight(font))}"
    }
    return if (font.supportsCjk) capability else "仅拉丁 · $capability"
}

private const val FONT_PREVIEW_COMPACT = "洛书字体 · Aa 0123456789"
private const val FONT_PREVIEW_DETAILED = "洛书字体 · Aa 0123456789\n天地玄黄 · Hello"

internal fun fontPreviewText(font: FontItem, detailed: Boolean = false): String {
    // 卡片样张必须保持完全一致，字体能力差异由下方能力条表达。
    // 仅拉丁字体的中文会按 Android 正常 fallback 显示，但不再改变卡片文案和高度。
    @Suppress("UNUSED_VARIABLE")
    val supportsCjk = font.supportsCjk
    return if (detailed) FONT_PREVIEW_DETAILED else FONT_PREVIEW_COMPACT
}

internal fun fontRoleWeight(role: String): Int = when (role.lowercase()) {
    "thin" -> 100
    "extralight" -> 200
    "light" -> 300
    "regular", "normal" -> 400
    "medium" -> 500
    "semibold" -> 600
    "bold" -> 700
    "extrabold" -> 800
    "black", "heavy" -> 900
    else -> role.toIntOrNull()?.coerceIn(1, 1000) ?: 400
}

internal fun fontWeightName(weight: Int): String = when (weight) {
    100 -> "极细 100"
    200 -> "超细 200"
    300 -> "细体 300"
    400 -> "常规 400"
    500 -> "中等 500"
    600 -> "半粗 600"
    700 -> "粗体 700"
    800 -> "特粗 800"
    900 -> "黑体 900"
    else -> weight.toString()
}

internal fun fontAxisDisplayName(tag: String): String = when (tag) {
    "wght" -> "字重"
    "wdth" -> "字宽"
    "opsz" -> "光学尺寸"
    "slnt" -> "倾斜"
    "ital" -> "斜体"
    "GRAD" -> "笔画等级"
    else -> "设计轴"
}

internal fun fontAxisValueLabel(value: Float): String =
    if (value % 1f == 0f) value.roundToInt().toString()
    else value.toString().trimEnd('0').trimEnd('.')

internal fun selectedFontId(state: MixState, slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> state.cjk
    MixSlot.Latin -> state.latin
    MixSlot.Digit -> state.digit
}

internal fun selectedWeight(state: MixState, slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> state.cjkWeight
    MixSlot.Latin -> state.latinWeight
    MixSlot.Digit -> state.digitWeight
}

internal fun selectedAxes(state: MixState, slot: MixSlot): Map<String, Float> = when (slot) {
    MixSlot.Cjk -> state.cjkAxes
    MixSlot.Latin -> state.latinAxes
    MixSlot.Digit -> state.digitAxes
}

internal fun directApplyFontId(state: MixState): String? {
    val ids = listOf(state.cjk, state.latin, state.digit)
    if (ids.any { it.isBlank() } || ids.distinct().size != 1) return null
    if (listOf(state.cjkWeight, state.latinWeight, state.digitWeight).any { it != 400 }) return null
    val standard = listOf(state.cjkAxes, state.latinAxes, state.digitAxes).all { axes ->
        axes.all { (tag, value) -> tag == "wght" && abs(value - 400f) < .5f }
    }
    return ids.first().takeIf { standard }
}
