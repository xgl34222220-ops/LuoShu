package io.github.xgl34222220.luoshu.ui.font

import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.fontAxisRepository
import io.github.xgl34222220.luoshu.resolveFontAxisInfo
import io.github.xgl34222220.luoshu.sourceRevision
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.math.roundToInt

internal fun cachedFontDefaultWeight(font: FontItem): Int? = fontAxisRepository.cached(font.sourceRevision)
    ?.axes?.firstOrNull { it.tag == "wght" }?.default
    ?.takeIf { it.isFinite() }
    ?.roundToInt()
    ?.coerceIn(1, 1000)

internal suspend fun resolveAndCacheFontDefaultAxes(font: FontItem): Map<String, Float> {
    if (!font.variable) {
        val weights = fontStaticWeights(font)
        val weight = when {
            400 in weights -> 400
            weights.isNotEmpty() -> weights.first()
            else -> 400
        }
        return mapOf("wght" to weight.toFloat())
    }
    // Keep the picker's existing 20 s total budget, including waiting for an
    // axis control already reading this revision. Never cache an error fallback.
    val info = withTimeoutOrNull(20_000L) { resolveFontAxisInfo(font) }
    return if (info != null && !info.loading && info.error.isBlank()) {
        info.axes.associate { it.tag to it.default }
    } else mapOf("wght" to 400f)
}
