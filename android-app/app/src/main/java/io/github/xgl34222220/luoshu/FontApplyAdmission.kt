package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import org.json.JSONObject

/** Foreground admission only; complete validation belongs to the supervised task. */
internal suspend fun admitFontApply(
    bridge: String,
    fontId: String,
    preflight: suspend (String) -> ShellResult,
    execute: suspend (String, Long) -> ShellResult,
    diagnostic: (String, Long, Int) -> Unit = { _, _, _ -> },
): String {
    suspend fun measured(stage: String, call: suspend () -> ShellResult): ShellResult {
        val started = System.nanoTime()
        var code = 127
        try {
            return call().also { code = it.code }
        } catch (cancelled: CancellationException) {
            code = 130
            throw cancelled
        } finally {
            diagnostic(stage, (System.nanoTime() - started) / 1_000_000L, code)
        }
    }
    fun response(result: ShellResult, fallback: String): JSONObject {
        if (result.code != 0) {
            // The request supervisor writes ownership diagnostics to stderr.
            // Prefer the worker's structured rejection instead of exposing logs.
            val rejection = result.stdout.lineSequence()
                .mapNotNull { line -> runCatching { JSONObject(line.trim()) }.getOrNull() }
                .firstOrNull { it.optString("status") == "error" }
                ?.optString("message").orEmpty()
            error(rejection.ifBlank { result.stderr.ifBlank { fallback } })
        }
        val line = result.stdout.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
            ?: error("未收到 JSON 数据")
        val root = JSONObject(line.trim())
        if (root.optString("status") != "ok") error(root.optString("message", fallback))
        return root
    }

    val fingerprint = if (fontId == "default") "" else {
        val root = response(measured("preflight") { preflight(fontId) }, "字体预检失败")
        val data = root.optJSONObject("data") ?: error("字体预检数据缺失")
        if (!data.optBoolean("valid", false)) error(data.optString("error", "字体文件不可用"))
        data.optString("fingerprint").also {
            if (!it.matches(Regex("font-selection-v1:[0-9a-f]{64}"))) error("字体预检身份缺失")
        }
    }
    val command = "sh ${RootShell.quote(bridge)} switch_start ${RootShell.quote(fontId)} ${RootShell.quote(fingerprint)}"
    val started = response(measured("admission") { execute(command, 20_000L) }, "无法启动字体切换")
    return started.optJSONObject("data")?.optString("task").orEmpty().also {
        if (it.isBlank()) error("字体任务 ID 缺失")
    }
}
