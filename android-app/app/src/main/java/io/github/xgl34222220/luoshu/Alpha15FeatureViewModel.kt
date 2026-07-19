package io.github.xgl34222220.luoshu

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import kotlin.math.roundToInt

internal data class SystemWeightState(
    val loading: Boolean = true,
    val supported: Boolean = false,
    val weight: Int = 400,
    val adjustment: Int = 0,
    val originalAdjustment: Int = 0,
    val min: Int = 300,
    val max: Int = 700,
    val step: Int = 10,
    val applying: Boolean = false,
    val message: String = "正在读取系统字体粗细…",
    val error: String = "",
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
    private val fontManager = "/data/adb/modules/LuoShu/common/font_manager.sh"
    private val coverageTool = "/data/adb/modules/LuoShu/common/font_coverage.sh"
    private var weightJob: Job? = null
    private var lastCommittedWeight: Int? = null

    var systemWeight by mutableStateOf(SystemWeightState())
        private set

    var coverage by mutableStateOf(CoverageProbeState())
        private set

    fun refreshSystemWeight() {
        if (systemWeight.applying) return
        systemWeight = systemWeight.copy(loading = true, error = "")
        viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(fontManager)} action font_weight_status",
                timeoutMs = 20_000L,
            )
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "系统字体粗细读取失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "系统字体粗细读取失败"))
                val data = root.getJSONObject("data")
                val minimum = data.optInt("min", 300)
                val maximum = data.optInt("max", 700).coerceAtLeast(minimum)
                val step = data.optInt("step", 10).coerceAtLeast(1)
                val weight = data.optInt("weight", 400).coerceIn(minimum, maximum)
                lastCommittedWeight = weight
                systemWeight = SystemWeightState(
                    loading = false,
                    supported = data.optBoolean("supported", false),
                    weight = weight,
                    adjustment = data.optInt("adjustment", weight - 400),
                    originalAdjustment = data.optInt("originalAdjustment", 0),
                    min = minimum,
                    max = maximum,
                    step = step,
                    message = "拖动后会自动写入，未刷新的应用重新打开即可",
                )
            } catch (error: Throwable) {
                systemWeight = systemWeight.copy(
                    loading = false,
                    supported = false,
                    error = error.message ?: "系统字体粗细读取失败",
                    message = "",
                )
            }
        }
    }

    fun previewSystemWeight(value: Float) {
        val state = systemWeight
        if (!state.supported || state.loading) return
        val snapped = snapWeight(value.roundToInt(), state.min, state.max, state.step)
        systemWeight = state.copy(
            weight = snapped,
            adjustment = snapped - 400,
            message = "正在等待滑动结束…",
            error = "",
        )
        weightJob?.cancel()
        weightJob = viewModelScope.launch {
            delay(360L)
            commitSystemWeight(snapped)
        }
    }

    fun commitSystemWeight(weight: Int = systemWeight.weight) {
        val state = systemWeight
        if (!state.supported || state.loading) return
        val safe = snapWeight(weight, state.min, state.max, state.step)
        if (lastCommittedWeight == safe && !state.error.isNotBlank()) {
            systemWeight = state.copy(message = "当前已是 $safe；未刷新的应用重新打开即可")
            return
        }
        weightJob?.cancel()
        weightJob = viewModelScope.launch {
            systemWeight = systemWeight.copy(
                weight = safe,
                adjustment = safe - 400,
                applying = true,
                message = "正在应用系统粗细 $safe…",
                error = "",
            )
            val result = RootShell.exec(
                "sh ${RootShell.quote(fontManager)} action font_weight_set ${RootShell.quote(safe.toString())}",
                timeoutMs = 20_000L,
            )
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "无法写入系统字体粗细" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "无法写入系统字体粗细"))
                val data = root.optJSONObject("data")
                val applied = data?.optInt("weight", safe) ?: safe
                lastCommittedWeight = applied
                systemWeight = systemWeight.copy(
                    weight = applied,
                    adjustment = data?.optInt("adjustment", applied - 400) ?: (applied - 400),
                    applying = false,
                    message = data?.optString("message").orEmpty().ifBlank {
                        "系统粗细已更新；未刷新的应用请重新打开"
                    },
                    error = "",
                )
            } catch (error: Throwable) {
                systemWeight = systemWeight.copy(
                    applying = false,
                    message = "",
                    error = error.message ?: "无法写入系统字体粗细",
                )
            }
        }
    }

    fun resetSystemWeight() {
        if (systemWeight.loading || systemWeight.applying) return
        weightJob?.cancel()
        weightJob = viewModelScope.launch {
            systemWeight = systemWeight.copy(applying = true, message = "正在恢复系统原始粗细…", error = "")
            val result = RootShell.exec(
                "sh ${RootShell.quote(fontManager)} action font_weight_reset",
                timeoutMs = 20_000L,
            )
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "无法恢复系统字体粗细" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "无法恢复系统字体粗细"))
                systemWeight = systemWeight.copy(applying = false)
                refreshSystemWeight()
            } catch (error: Throwable) {
                systemWeight = systemWeight.copy(
                    applying = false,
                    message = "",
                    error = error.message ?: "无法恢复系统字体粗细",
                )
            }
        }
    }

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

    private fun snapWeight(value: Int, min: Int, max: Int, step: Int): Int {
        val safeStep = step.coerceAtLeast(1)
        val snapped = min + (((value.coerceIn(min, max) - min).toFloat() / safeStep).roundToInt() * safeStep)
        return snapped.coerceIn(min, max)
    }

    private fun firstJson(raw: String): JSONObject {
        val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
            ?: error("未收到 JSON 数据")
        return JSONObject(line.trim())
    }
}
