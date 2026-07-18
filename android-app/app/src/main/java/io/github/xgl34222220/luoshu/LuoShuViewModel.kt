package io.github.xgl34222220.luoshu

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import org.json.JSONObject

internal data class ModuleSnapshot(
    val loading: Boolean = true,
    val rootGranted: Boolean = false,
    val installed: Boolean = false,
    val version: String = "检测中…",
    val versionCode: Int = 0,
    val activeFont: String = "default",
    val taskState: String = "idle",
    val taskMessage: String = "暂无后台任务",
    val rootManager: String = "未知",
    val mountEngine: String = "未知",
    val error: String = "",
) {
    val activeLabel: String
        get() = when (activeFont) {
            "mix" -> "完整复合字体"
            "default", "" -> "系统默认字体"
            else -> activeFont
        }
}

internal class LuoShuViewModel : ViewModel() {
    var snapshot by mutableStateOf(ModuleSnapshot())
        private set

    var logs by mutableStateOf("正在读取日志…")
        private set

    fun refresh() {
        snapshot = snapshot.copy(loading = true, error = "")
        viewModelScope.launch {
            val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"
            val result = RootShell.exec(
                "if [ -f ${RootShell.quote(bridge)} ]; then sh ${RootShell.quote(bridge)} status; " +
                    "else printf '%s\\n' '{\"status\":\"error\",\"message\":\"模块版本尚未提供 App 桥\"}'; fi",
                timeoutMs = 30_000L,
            )

            if (result.code != 0) {
                snapshot = ModuleSnapshot(
                    loading = false,
                    rootGranted = false,
                    error = result.stderr.ifBlank { "Root 授权失败或 su 不可用" },
                )
                logs = "无法读取日志：尚未获得 Root 授权。"
                return@launch
            }

            snapshot = parseSnapshot(result.stdout)
            refreshLogs()
        }
    }

    fun refreshLogs() {
        viewModelScope.launch {
            val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"
            val result = RootShell.exec(
                "if [ -f ${RootShell.quote(bridge)} ]; then sh ${RootShell.quote(bridge)} logs 180; " +
                    "else tail -n 180 /data/adb/modules/LuoShu/logs/fontswitch.log 2>/dev/null; fi",
                timeoutMs = 20_000L,
            )
            logs = when {
                result.code != 0 -> result.stderr.ifBlank { "日志读取失败" }
                result.stdout.isBlank() -> "当前还没有字体任务日志。"
                else -> result.stdout.trimEnd()
            }
        }
    }

    private fun parseSnapshot(raw: String): ModuleSnapshot {
        return try {
            val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
                ?: error("未收到模块状态")
            val root = JSONObject(line)
            if (root.optString("status") != "ok") {
                return ModuleSnapshot(
                    loading = false,
                    rootGranted = true,
                    error = root.optString("message", "模块状态读取失败"),
                )
            }
            val data = root.getJSONObject("data")
            ModuleSnapshot(
                loading = false,
                rootGranted = data.optBoolean("root", true),
                installed = data.optBoolean("installed", false),
                version = data.optString("version", "未知版本"),
                versionCode = data.optInt("versionCode", 0),
                activeFont = data.optString("active", "default"),
                taskState = data.optString("taskState", "idle"),
                taskMessage = data.optString("taskMessage", "暂无后台任务"),
                rootManager = data.optString("rootManager", "Root"),
                mountEngine = data.optString("mountEngine", "原生模块挂载"),
            )
        } catch (error: Throwable) {
            ModuleSnapshot(
                loading = false,
                rootGranted = true,
                error = error.message ?: "模块状态解析失败",
            )
        }
    }
}
