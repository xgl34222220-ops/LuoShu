package io.github.xgl34222220.luoshu

import org.json.JSONObject
import kotlin.math.roundToInt

internal data class VariableAxisInfo(
    val tag: String,
    val min: Float,
    val default: Float,
    val max: Float,
    val name: String = "",
    val hidden: Boolean = false,
)

internal data class WeightAxisInfo(
    val loading: Boolean = true,
    val hasWeight: Boolean = false,
    val min: Int = 100,
    val default: Int = 400,
    val max: Int = 900,
    val axes: List<VariableAxisInfo> = emptyList(),
    val error: String = "",
) {
    val visibleAxes: List<VariableAxisInfo> get() = axes.filterNot { it.hidden }
}

/** Font-declared capability only; malformed metadata cannot become a slider. */
internal fun parseWeightAxisInfo(root: JSONObject): WeightAxisInfo {
    require(root.optString("status") == "ok") { root.optString("message", "字体轴读取失败") }
    val rawAxes = root.optJSONArray("axes") ?: error("未收到字体轴列表")
    require(rawAxes.length() <= 64) { "字体轴数量异常" }
    val seen = mutableSetOf<String>()
    val axes = buildList {
        for (index in 0 until rawAxes.length()) {
            val axis = rawAxes.optJSONObject(index) ?: error("字体轴数据无效")
            val tag = axis.optString("tag")
            val minimum = axis.optDouble("min", Double.NaN).toFloat()
            val maximum = axis.optDouble("max", Double.NaN).toFloat()
            val default = axis.optDouble("default", Double.NaN).toFloat()
            require(
                tag.length == 4 && tag.all { it.code in 32..126 } && seen.add(tag) &&
                    minimum.isFinite() && maximum.isFinite() && default.isFinite() &&
                    minimum <= default && default <= maximum,
            ) { "字体轴 $tag 的定义无效" }
            val name = axis.optString("name").map {
                if (it.isISOControl() || it == '\u2028' || it == '\u2029') ' ' else it
            }.joinToString("").trim().take(128)
            add(VariableAxisInfo(tag, minimum, default, maximum, name, axis.optBoolean("hidden", false)))
        }
    }
    val weight = axes.firstOrNull { it.tag == "wght" }
    return WeightAxisInfo(
        loading = false,
        hasWeight = weight != null,
        min = weight?.min?.roundToInt() ?: 100,
        default = weight?.default?.roundToInt() ?: 400,
        max = weight?.max?.roundToInt() ?: 900,
        axes = axes,
    )
}
