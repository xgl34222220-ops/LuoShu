package io.github.xgl34222220.luoshu.ui.font

import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.RootShell
import org.json.JSONObject
import kotlin.math.roundToInt

private val defaultAxisCache = mutableMapOf<String, Map<String, Float>>()
private val defaultAxisLock = Any()

internal fun cacheFontDefaultAxes(fontId: String, axes: Map<String, Float>) {
    if (fontId.isBlank()) return
    val clean = axes.filter { (tag, value) -> tag.length == 4 && value.isFinite() }
        .ifEmpty { mapOf("wght" to 400f) }
    synchronized(defaultAxisLock) {
        defaultAxisCache[fontId] = clean
    }
}

internal fun cachedFontDefaultAxes(fontId: String): Map<String, Float>? = synchronized(defaultAxisLock) {
    defaultAxisCache[fontId]
}

internal fun cachedFontDefaultWeight(fontId: String): Int? = cachedFontDefaultAxes(fontId)
    ?.get("wght")
    ?.takeIf { it.isFinite() }
    ?.roundToInt()
    ?.coerceIn(1, 1000)

internal suspend fun resolveAndCacheFontDefaultAxes(font: FontItem): Map<String, Float> {
    val cached = cachedFontDefaultAxes(font.id)
    if (cached != null) return cached
    return resolveFontDefaultAxes(font).also { cacheFontDefaultAxes(font.id, it) }
}

internal suspend fun resolveFontDefaultAxes(font: FontItem): Map<String, Float> {
    if (!font.variable) {
        val weights = fontStaticWeights(font)
        val weight = when {
            400 in weights -> 400
            weights.isNotEmpty() -> weights.first()
            else -> 400
        }
        return mapOf("wght" to weight.toFloat())
    }
    val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"
    val result = RootShell.exec(
        "sh ${RootShell.quote(bridge)} weight_axis ${RootShell.quote(font.id)}",
        timeoutMs = 20_000L,
    )
    if (result.code != 0) return mapOf("wght" to 400f)
    return runCatching {
        val line = result.stdout.lineSequence().first { it.trimStart().startsWith("{") }
        val root = JSONObject(line.trim())
        if (root.optString("status") != "ok") return@runCatching mapOf("wght" to 400f)
        val axes = linkedMapOf<String, Float>()
        val array = root.optJSONArray("axes")
        if (array != null) {
            for (index in 0 until array.length()) {
                val axis = array.optJSONObject(index) ?: continue
                val tag = axis.optString("tag")
                val value = axis.optDouble("default", Double.NaN).toFloat()
                if (tag.length == 4 && value.isFinite()) axes[tag] = value
            }
        }
        if ("wght" !in axes) axes["wght"] = 400f
        axes.toMap()
    }.getOrElse { mapOf("wght" to 400f) }
}
