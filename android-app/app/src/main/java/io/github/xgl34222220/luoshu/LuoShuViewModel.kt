package io.github.xgl34222220.luoshu

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
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

internal data class FontItem(
    val id: String,
    val name: String,
    val format: String,
    val size: String,
    val date: String,
    val variable: Boolean,
    val valid: Boolean,
    val error: String,
    val weights: List<String>,
) {
    val weightLabel: String
        get() = when {
            variable -> "可变字体"
            weights.isEmpty() -> "单字重"
            else -> weights.joinToString(" · ") { role ->
                when (role) {
                    "thin" -> "极细"
                    "light" -> "细体"
                    "regular" -> "常规"
                    "medium" -> "中等"
                    "semibold" -> "半粗"
                    "bold" -> "粗体"
                    "black" -> "特粗"
                    else -> role
                }
            }
        }
}

internal class LuoShuViewModel : ViewModel() {
    private val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"

    var snapshot by mutableStateOf(ModuleSnapshot())
        private set

    var logs by mutableStateOf("正在读取日志…")
        private set

    var fonts by mutableStateOf<List<FontItem>>(emptyList())
        private set

    var fontLoading by mutableStateOf(false)
        private set

    var fontError by mutableStateOf("")
        private set

    private var _searchQuery by mutableStateOf("")
    val searchQuery: String
        get() = _searchQuery

    var operationBusy by mutableStateOf(false)
        private set

    var operationMessage by mutableStateOf("")
        private set

    var rebootRequired by mutableStateOf(false)
        private set

    val filteredFonts: List<FontItem>
        get() {
            val query = searchQuery.trim()
            if (query.isEmpty()) return fonts
            return fonts.filter { item ->
                item.name.contains(query, ignoreCase = true) ||
                    item.id.contains(query, ignoreCase = true) ||
                    item.format.contains(query, ignoreCase = true)
            }
        }

    fun setSearchQuery(value: String) {
        _searchQuery = value
    }

    fun refresh() {
        snapshot = snapshot.copy(loading = true, error = "")
        viewModelScope.launch {
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
            refreshFonts()
            refreshLogs()
        }
    }

    fun refreshFonts(force: Boolean = false) {
        if (fontLoading) return
        fontLoading = true
        fontError = ""
        viewModelScope.launch {
            val suffix = if (force) " refresh" else ""
            val result = RootShell.exec(
                "sh ${RootShell.quote(bridge)} fonts$suffix",
                timeoutMs = 90_000L,
            )
            if (result.code != 0) {
                fontError = result.stderr.ifBlank { "字体库读取失败" }
                fontLoading = false
                return@launch
            }
            try {
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "字体库读取失败"))
                val data = root.getJSONObject("data")
                snapshot = snapshot.copy(activeFont = data.optString("current", snapshot.activeFont))
                fonts = parseFonts(data.optJSONArray("fonts") ?: JSONArray())
            } catch (error: Throwable) {
                fontError = error.message ?: "字体库解析失败"
            } finally {
                fontLoading = false
            }
        }
    }

    fun applyFont(fontId: String) {
        if (operationBusy) return
        operationBusy = true
        operationMessage = if (fontId == "default") "正在准备恢复系统字体…" else "正在验证并应用字体…"
        viewModelScope.launch {
            try {
                if (fontId != "default") {
                    val validation = RootShell.exec(
                        "sh ${RootShell.quote(bridge)} validate ${RootShell.quote(fontId)}",
                        timeoutMs = 45_000L,
                    )
                    if (validation.code != 0) error(validation.stderr.ifBlank { "字体验证失败" })
                    val validationJson = firstJson(validation.stdout)
                    if (validationJson.optString("status") != "ok" || validationJson.optJSONObject("data")?.optBoolean("valid", true) == false) {
                        error(validationJson.optString("message", validationJson.optJSONObject("data")?.optString("error", "字体文件不可用") ?: "字体文件不可用"))
                    }
                }

                val start = RootShell.exec(
                    "sh ${RootShell.quote(bridge)} switch_start ${RootShell.quote(fontId)}",
                    timeoutMs = 45_000L,
                )
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动字体切换" })
                val startJson = firstJson(start.stdout)
                if (startJson.optString("status") != "ok") error(startJson.optString("message", "无法启动字体切换"))
                val taskId = startJson.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("字体任务 ID 缺失")

                val result = waitForTask(taskId)
                if (result.optString("state") != "success") error(result.optString("message", "字体应用失败"))

                snapshot = snapshot.copy(
                    activeFont = fontId,
                    taskState = "success",
                    taskMessage = result.optString("message", "字体已准备完成"),
                )
                operationMessage = if (fontId == "default") "已准备恢复系统字体，重启后生效" else "字体已准备完成，重启后全局生效"
                rebootRequired = true
                refreshFonts()
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体应用失败"
                snapshot = snapshot.copy(taskState = "failed", taskMessage = operationMessage)
            } finally {
                operationBusy = false
            }
        }
    }

    fun deleteFont(fontId: String) {
        if (operationBusy || fontId.isBlank() || fontId == "default") return
        operationBusy = true
        operationMessage = "正在删除字体…"
        viewModelScope.launch {
            try {
                val result = RootShell.exec(
                    "sh ${RootShell.quote(bridge)} delete ${RootShell.quote(fontId)}",
                    timeoutMs = 45_000L,
                )
                if (result.code != 0) error(result.stderr.ifBlank { "字体删除失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "字体删除失败"))
                operationMessage = "字体已删除"
                refreshFonts(force = true)
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体删除失败"
            } finally {
                operationBusy = false
            }
        }
    }

    fun rebootDevice() {
        if (operationBusy) return
        operationBusy = true
        operationMessage = "正在请求重启…"
        viewModelScope.launch {
            val result = RootShell.exec("sh ${RootShell.quote(bridge)} reboot", timeoutMs = 20_000L)
            if (result.code != 0) {
                operationMessage = result.stderr.ifBlank { "重启请求失败" }
                operationBusy = false
            }
        }
    }

    fun refreshLogs() {
        viewModelScope.launch {
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

    private suspend fun waitForTask(taskId: String): JSONObject {
        repeat(120) {
            delay(650L)
            val status = RootShell.exec(
                "sh ${RootShell.quote(bridge)} switch_status ${RootShell.quote(taskId)}",
                timeoutMs = 20_000L,
            )
            if (status.code != 0) return@repeat
            val root = runCatching { firstJson(status.stdout) }.getOrNull() ?: return@repeat
            val data = root.optJSONObject("data") ?: return@repeat
            val state = data.optString("state")
            operationMessage = data.optString("message", "正在处理字体…")
            snapshot = snapshot.copy(taskState = state.ifBlank { "running" }, taskMessage = operationMessage)
            if (state == "success" || state == "failed") return data
        }
        error("字体任务超时，请查看日志")
    }

    private fun parseSnapshot(raw: String): ModuleSnapshot {
        return try {
            val root = firstJson(raw)
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

    private fun parseFonts(array: JSONArray): List<FontItem> = buildList {
        for (index in 0 until array.length()) {
            val item = array.optJSONObject(index) ?: continue
            val id = item.optString("id")
            if (id.isBlank() || id == "default") continue
            val weightsArray = item.optJSONArray("weights")
            val weights = buildList {
                if (weightsArray != null) for (weightIndex in 0 until weightsArray.length()) {
                    weightsArray.optString(weightIndex).takeIf { it.isNotBlank() }?.let(::add)
                }
            }
            add(
                FontItem(
                    id = id,
                    name = item.optString("name", id),
                    format = item.optString("format", "TTF"),
                    size = item.optString("size", ""),
                    date = item.optString("date", ""),
                    variable = item.optBoolean("variable", weights.contains("variable")),
                    valid = item.optBoolean("valid", true),
                    error = item.optString("error", ""),
                    weights = weights,
                ),
            )
        }
    }

    private fun firstJson(raw: String): JSONObject {
        val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
            ?: error("未收到 JSON 数据")
        return JSONObject(line.trim())
    }
}
