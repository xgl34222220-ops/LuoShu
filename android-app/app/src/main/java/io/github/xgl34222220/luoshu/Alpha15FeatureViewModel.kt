package io.github.xgl34222220.luoshu

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import org.json.JSONObject

internal data class CoverageGroupMetrics(
    val present: Int = 0,
    val total: Int = 0,
    val percent: Float = 0f,
)

internal data class CoverageMetrics(
    val glyphs: Int = 0,
    val cjkPresent: Int = 0,
    val cjkTotal: Int = 0,
    val latinPresent: Int = 0,
    val latinTotal: Int = 0,
    val digitPresent: Int = 0,
    val digitTotal: Int = 0,
    val punctuationPresent: Int = 0,
    val punctuationTotal: Int = 0,
    val missingSample: String = "",
    val groups: Map<String, CoverageGroupMetrics> = emptyMap(),
    val missingByGroup: Map<String, String> = emptyMap(),
    val recommendation: String = "",
) {
    val cjkRatio: Float get() = ratio(cjkPresent, cjkTotal)
    val latinRatio: Float get() = ratio(latinPresent, latinTotal)
    val digitRatio: Float get() = ratio(digitPresent, digitTotal)
    val punctuationRatio: Float get() = ratio(punctuationPresent, punctuationTotal)

    private fun ratio(present: Int, total: Int): Float =
        if (total <= 0) 0f else (present.toFloat() / total.toFloat()).coerceIn(0f, 1f)
}

internal data class CoverageProbeState(
    val loading: Boolean = false,
    val fontId: String = "",
    val metrics: CoverageMetrics? = null,
    val error: String = "",
)

internal class Alpha15FeatureViewModel : ViewModel() {
    private val coverageTool = "/data/adb/modules/LuoShu/common/font_coverage.sh"

    var coverage by mutableStateOf(CoverageProbeState())
        private set

    fun inspectCoverage(fontId: String) {
        if (fontId.isBlank() || coverage.loading) return
        coverage = CoverageProbeState(loading = true, fontId = fontId)
        viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(coverageTool)} ${RootShell.quote(fontId)}",
                timeoutMs = 35_000L,
            )
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "字体覆盖诊断失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "字体覆盖诊断失败"))
                val data = root.getJSONObject("data")
                coverage = CoverageProbeState(
                    loading = false,
                    fontId = fontId,
                    metrics = CoverageMetrics(
                        glyphs = data.optInt("glyphs", 0),
                        cjkPresent = data.optJSONObject("cjk")?.optInt("present", 0) ?: 0,
                        cjkTotal = data.optJSONObject("cjk")?.optInt("total", 0) ?: 0,
                        latinPresent = data.optJSONObject("latin")?.optInt("present", 0) ?: 0,
                        latinTotal = data.optJSONObject("latin")?.optInt("total", 0) ?: 0,
                        digitPresent = data.optJSONObject("digit")?.optInt("present", 0) ?: 0,
                        digitTotal = data.optJSONObject("digit")?.optInt("total", 0) ?: 0,
                        punctuationPresent = data.optJSONObject("punctuation")?.optInt("present", 0) ?: 0,
                        punctuationTotal = data.optJSONObject("punctuation")?.optInt("total", 0) ?: 0,
                        missingSample = data.optString("missingSample", ""),
                        groups = parseCoverageGroups(data.optJSONObject("groups")),
                        missingByGroup = parseMissingGroups(data.optJSONObject("missingByGroup")),
                        recommendation = data.optString("recommendation", ""),
                    ),
                )
            } catch (error: Throwable) {
                coverage = CoverageProbeState(
                    loading = false,
                    fontId = fontId,
                    error = error.message ?: "字体覆盖诊断失败",
                )
            }
        }
    }

    private fun parseCoverageGroups(root: JSONObject?): Map<String, CoverageGroupMetrics> {
        if (root == null) return emptyMap()
        return buildMap {
            val keys = root.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                val item = root.optJSONObject(key) ?: continue
                put(
                    key,
                    CoverageGroupMetrics(
                        present = item.optInt("present", 0),
                        total = item.optInt("total", 0),
                        percent = item.optDouble("percent", 0.0).toFloat().coerceIn(0f, 100f),
                    ),
                )
            }
        }
    }

    private fun parseMissingGroups(root: JSONObject?): Map<String, String> {
        if (root == null) return emptyMap()
        return buildMap {
            val keys = root.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                root.optString(key).takeIf { it.isNotBlank() }?.let { put(key, it) }
            }
        }
    }

    private fun firstJson(raw: String): JSONObject {
        val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
            ?: error("未收到 JSON 数据")
        return JSONObject(line.trim())
    }
}
