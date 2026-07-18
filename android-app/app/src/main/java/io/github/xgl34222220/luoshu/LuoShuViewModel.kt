package io.github.xgl34222220.luoshu

import android.content.Context
import android.net.Uri
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
                when (role.lowercase()) {
                    "thin" -> "极细 100"
                    "extralight", "ultralight" -> "超细 200"
                    "light" -> "细体 300"
                    "regular", "normal" -> "常规 400"
                    "medium" -> "中等 500"
                    "semibold", "demibold" -> "半粗 600"
                    "bold" -> "粗体 700"
                    "extrabold", "ultrabold" -> "特粗 800"
                    "black", "heavy" -> "黑体 900"
                    else -> role
                }
            }
        }
}

internal enum class MixSlot { Cjk, Latin, Digit }

internal data class MixState(
    val loading: Boolean = false,
    val cjk: String = "",
    val latin: String = "",
    val digit: String = "",
    val cjkWeight: Int = 400,
    val latinWeight: Int = 400,
    val digitWeight: Int = 400,
    val cjkAuto: Boolean = true,
    val latinAuto: Boolean = true,
    val digitAuto: Boolean = true,
    val enabled: Boolean = false,
    val busy: Boolean = false,
    val taskId: String = "",
    val taskState: String = "idle",
    val message: String = "请选择中文、英文和数字字体",
    val progress: Int = 0,
    val error: String = "",
)

internal class LuoShuViewModel : ViewModel() {
    private val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"

    var snapshot by mutableStateOf(ModuleSnapshot())
        private set
    var logs by mutableStateOf("尚未读取日志")
        private set
    var fonts by mutableStateOf<List<FontItem>>(emptyList())
        private set
    var fontLoading by mutableStateOf(false)
        private set
    var fontError by mutableStateOf("")
        private set
    private var _searchQuery by mutableStateOf("")
    val searchQuery: String get() = _searchQuery
    var operationBusy by mutableStateOf(false)
        private set
    var operationMessage by mutableStateOf("")
        private set
    var rebootRequired by mutableStateOf(false)
        private set
    var mixState by mutableStateOf(MixState())
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

    fun setSearchQuery(value: String) { _searchQuery = value }

    fun refresh() {
        snapshot = snapshot.copy(loading = true, error = "")
        viewModelScope.launch {
            val result = RootShell.exec(
                "if [ -f ${RootShell.quote(bridge)} ]; then sh ${RootShell.quote(bridge)} status; " +
                    "else printf '%s\\n' '{\"status\":\"error\",\"message\":\"请先刷入匹配的 Hybrid Bridge 模块\"}'; fi",
                timeoutMs = 20_000L,
            )
            if (result.code != 0) {
                snapshot = ModuleSnapshot(loading = false, rootGranted = false, error = result.stderr.ifBlank { "Root 授权失败或 su 不可用" })
                return@launch
            }
            snapshot = parseSnapshot(result.stdout)
        }
    }

    fun ensureFonts(force: Boolean = false) { if (fonts.isEmpty() || force) refreshFonts(force) }

    fun refreshFonts(force: Boolean = false) {
        if (fontLoading) return
        fontLoading = true
        fontError = ""
        viewModelScope.launch {
            val suffix = if (force) " refresh" else ""
            val result = RootShell.exec("sh ${RootShell.quote(bridge)} fonts$suffix", timeoutMs = 90_000L)
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
                normalizeMixSelections()
            } catch (error: Throwable) {
                fontError = error.message ?: "字体库解析失败"
            } finally {
                fontLoading = false
            }
        }
    }

    fun refreshMixConfig() {
        if (mixState.loading || mixState.busy) return
        mixState = mixState.copy(loading = true, error = "")
        viewModelScope.launch {
            val result = RootShell.exec("sh ${RootShell.quote(bridge)} mix_config", timeoutMs = 25_000L)
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "组合配置读取失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "组合配置读取失败"))
                val data = root.getJSONObject("data")
                mixState = mixState.copy(
                    loading = false,
                    enabled = data.optBoolean("enabled", false),
                    cjk = data.optString("cjk", mixState.cjk),
                    latin = data.optString("latin", mixState.latin),
                    digit = data.optString("digit", mixState.digit),
                    cjkWeight = data.optInt("cjkWeight", mixState.cjkWeight).coerceIn(100, 900),
                    latinWeight = data.optInt("latinWeight", mixState.latinWeight).coerceIn(100, 900),
                    digitWeight = data.optInt("digitWeight", mixState.digitWeight).coerceIn(100, 900),
                    cjkAuto = data.optBoolean("cjkAuto", true),
                    latinAuto = data.optBoolean("latinAuto", true),
                    digitAuto = data.optBoolean("digitAuto", true),
                    message = if (data.optBoolean("enabled", false)) "当前正在使用复合字体" else "可直接生成新的复合字体",
                    error = "",
                )
                normalizeMixSelections()
            } catch (error: Throwable) {
                mixState = mixState.copy(loading = false, error = error.message ?: "组合配置读取失败")
            }
        }
    }

    fun updateMixFont(slot: MixSlot, fontId: String) {
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjk = fontId)
            MixSlot.Latin -> mixState.copy(latin = fontId)
            MixSlot.Digit -> mixState.copy(digit = fontId)
        }
    }

    fun updateMixWeight(slot: MixSlot, weight: Int) {
        val safe = (weight / 10 * 10).coerceIn(100, 900)
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjkWeight = safe)
            MixSlot.Latin -> mixState.copy(latinWeight = safe)
            MixSlot.Digit -> mixState.copy(digitWeight = safe)
        }
    }

    fun mixWeightAuto(slot: MixSlot): Boolean = when (slot) {
        MixSlot.Cjk -> mixState.cjkAuto
        MixSlot.Latin -> mixState.latinAuto
        MixSlot.Digit -> mixState.digitAuto
    }

    fun updateMixWeightAuto(slot: MixSlot, auto: Boolean) {
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjkAuto = auto)
            MixSlot.Latin -> mixState.copy(latinAuto = auto)
            MixSlot.Digit -> mixState.copy(digitAuto = auto)
        }
    }

    fun startMix() {
        if (mixState.busy || operationBusy) return
        val cjk = mixState.cjk
        val latin = mixState.latin
        val digit = mixState.digit
        if (cjk.isBlank() || latin.isBlank() || digit.isBlank()) {
            mixState = mixState.copy(error = "请先选择中文、英文和数字字体")
            return
        }
        mixState = mixState.copy(busy = true, taskState = "queued", message = "正在提交复合字体任务…", progress = 1, error = "")
        viewModelScope.launch {
            try {
                val command = buildString {
                    append("sh ${RootShell.quote(bridge)} mix_start ")
                    append(RootShell.quote(cjk)).append(' ')
                    append(RootShell.quote(latin)).append(' ')
                    append(RootShell.quote(digit)).append(' ')
                    append(RootShell.quote(if (mixState.cjkAuto) "auto" else "wght=${mixState.cjkWeight}")).append(' ')
                    append(RootShell.quote(if (mixState.latinAuto) "auto" else "wght=${mixState.latinWeight}")).append(' ')
                    append(RootShell.quote(if (mixState.digitAuto) "auto" else "wght=${mixState.digitWeight}"))
                }
                val start = RootShell.exec(command, timeoutMs = 20_000L)
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动复合字体任务" })
                val root = firstJson(start.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "无法启动复合字体任务"))
                val taskId = root.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("复合字体任务 ID 缺失")
                mixState = mixState.copy(taskId = taskId, taskState = "running", message = "复合字体正在后台生成")
                val final = waitForMixTask(taskId)
                if (final.optString("state") != "success") error(final.optString("message", "复合字体生成失败"))
                mixState = mixState.copy(busy = false, enabled = true, taskState = "success", message = final.optString("message", "复合字体已生成，重启后生效"), progress = 100)
                snapshot = snapshot.copy(activeFont = "mix", taskState = "success", taskMessage = mixState.message)
                rebootRequired = true
            } catch (error: Throwable) {
                mixState = mixState.copy(busy = false, taskState = "failed", message = error.message ?: "复合字体生成失败", error = error.message ?: "复合字体生成失败", progress = 100)
            }
        }
    }

    fun applyFont(fontId: String) {
        if (operationBusy || mixState.busy) return
        operationBusy = true
        operationMessage = if (fontId == "default") "正在准备恢复系统字体…" else "正在验证并应用字体…"
        viewModelScope.launch {
            try {
                if (fontId != "default") {
                    val validation = RootShell.exec("sh ${RootShell.quote(bridge)} validate ${RootShell.quote(fontId)}", timeoutMs = 35_000L)
                    if (validation.code != 0) error(validation.stderr.ifBlank { "字体验证失败" })
                    val validationJson = firstJson(validation.stdout)
                    if (validationJson.optString("status") != "ok" || validationJson.optJSONObject("data")?.optBoolean("valid", true) == false) {
                        error(validationJson.optString("message", validationJson.optJSONObject("data")?.optString("error", "字体文件不可用") ?: "字体文件不可用"))
                    }
                }
                val start = RootShell.exec("sh ${RootShell.quote(bridge)} switch_start ${RootShell.quote(fontId)}", timeoutMs = 20_000L)
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动字体切换" })
                val startJson = firstJson(start.stdout)
                if (startJson.optString("status") != "ok") error(startJson.optString("message", "无法启动字体切换"))
                val taskId = startJson.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("字体任务 ID 缺失")
                val result = waitForSwitchTask(taskId)
                if (result.optString("state") != "success") error(result.optString("message", "字体应用失败"))
                snapshot = snapshot.copy(activeFont = fontId, taskState = "success", taskMessage = result.optString("message", "字体已准备完成"))
                operationMessage = if (fontId == "default") "已准备恢复系统字体，重启后生效" else "字体已准备完成，重启后全局生效"
                rebootRequired = true
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体应用失败"
                snapshot = snapshot.copy(taskState = "failed", taskMessage = operationMessage)
            } finally {
                operationBusy = false
            }
        }
    }

    fun importFonts(context: Context, uris: List<Uri>) {
        if (operationBusy || mixState.busy) return
        val selected = uris.distinctBy(Uri::toString)
        if (selected.isEmpty()) return
        operationBusy = true
        operationMessage = "正在读取所选字体或模块包…"
        viewModelScope.launch {
            var staged = emptyList<StagedFontImport>()
            var refreshAfter = false
            try {
                staged = stageFontImports(context, selected)
                var imported = 0
                var duplicates = 0
                var failed = 0
                val errors = mutableListOf<String>()
                staged.forEachIndexed { index, item ->
                    operationMessage = if (item.isModulePackage) "正在解析字体模块 ${index + 1}/${staged.size}：${item.displayName}" else "正在导入 ${index + 1}/${staged.size}：${item.displayName}"
                    try {
                        val action = if (item.isModulePackage) "import_package" else "import"
                        val result = RootShell.exec(
                            "sh ${RootShell.quote(bridge)} $action ${RootShell.quote(item.file.absolutePath)} ${RootShell.quote(item.displayName)}",
                            timeoutMs = if (item.isModulePackage) 180_000L else 45_000L,
                        )
                        if (result.code != 0) error(result.stderr.ifBlank { "导入失败" })
                        val root = firstJson(result.stdout)
                        if (root.optString("status") != "ok") error(root.optString("message", "导入失败"))
                        val data = root.optJSONObject("data") ?: JSONObject()
                        if (item.isModulePackage) {
                            imported += data.optInt("imported", 0)
                            duplicates += data.optInt("duplicates", 0)
                            failed += data.optInt("failed", 0)
                            data.optString("firstError").takeIf(String::isNotBlank)?.let(errors::add)
                        } else {
                            if (data.optBoolean("imported", true)) imported += 1 else duplicates += 1
                        }
                    } catch (error: Throwable) {
                        failed += 1
                        errors += "${item.displayName}：${error.message ?: "导入失败"}"
                    }
                }
                refreshAfter = imported > 0 || duplicates > 0
                operationMessage = buildString {
                    append("导入完成：新增 $imported 个")
                    if (duplicates > 0) append("，跳过重复 $duplicates 个")
                    if (failed > 0) append("，失败 $failed 个")
                    if (errors.isNotEmpty()) append("（${errors.first()}）")
                }
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体导入失败"
            } finally {
                cleanupFontImports(staged)
                operationBusy = false
                if (refreshAfter) refreshFonts(force = true)
            }
        }
    }

    fun importInstalledFontModules() {
        if (operationBusy || mixState.busy) return
        operationBusy = true
        operationMessage = "正在扫描已安装的字体模块…"
        viewModelScope.launch {
            try {
                val result = RootShell.exec("sh ${RootShell.quote(bridge)} import_modules", timeoutMs = 240_000L)
                if (result.code != 0) error(result.stderr.ifBlank { "字体模块扫描失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "字体模块扫描失败"))
                val data = root.optJSONObject("data") ?: JSONObject()
                operationMessage = "识别 ${data.optInt("modules", 0)} 个字体模块：新增 ${data.optInt("imported", 0)} 个，重复 ${data.optInt("duplicates", 0)} 个，失败 ${data.optInt("failed", 0)} 个"
                refreshFonts(force = true)
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体模块扫描失败"
            } finally {
                operationBusy = false
            }
        }
    }

    fun deleteFont(fontId: String) {
        if (operationBusy || mixState.busy || fontId.isBlank() || fontId == "default") return
        operationBusy = true
        operationMessage = "正在删除字体…"
        viewModelScope.launch {
            try {
                val result = RootShell.exec("sh ${RootShell.quote(bridge)} delete ${RootShell.quote(fontId)}", timeoutMs = 35_000L)
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
        if (operationBusy || mixState.busy) return
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
                "if [ -f ${RootShell.quote(bridge)} ]; then sh ${RootShell.quote(bridge)} logs 180; else tail -n 180 /data/adb/modules/LuoShu/logs/fontswitch.log 2>/dev/null; fi",
                timeoutMs = 20_000L,
            )
            logs = when {
                result.code != 0 -> result.stderr.ifBlank { "日志读取失败" }
                result.stdout.isBlank() -> "当前还没有字体任务日志。"
                else -> result.stdout.trimEnd()
            }
        }
    }

    private fun normalizeMixSelections() {
        val available = fonts.filter { it.valid }
        if (available.isEmpty()) return
        val ids = available.map { it.id }.toSet()
        val first = available.first().id
        mixState = mixState.copy(
            cjk = mixState.cjk.takeIf { it in ids } ?: first,
            latin = mixState.latin.takeIf { it in ids } ?: available.getOrNull(1)?.id ?: first,
            digit = mixState.digit.takeIf { it in ids } ?: available.getOrNull(2)?.id ?: available.getOrNull(1)?.id ?: first,
        )
    }

    private suspend fun waitForSwitchTask(taskId: String): JSONObject {
        repeat(120) {
            delay(650L)
            val status = RootShell.exec("sh ${RootShell.quote(bridge)} switch_status ${RootShell.quote(taskId)}", timeoutMs = 15_000L)
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

    private suspend fun waitForMixTask(taskId: String): JSONObject {
        repeat(420) {
            delay(1_000L)
            val status = RootShell.exec("sh ${RootShell.quote(bridge)} mix_status ${RootShell.quote(taskId)}", timeoutMs = 15_000L)
            if (status.code != 0) return@repeat
            val root = runCatching { firstJson(status.stdout) }.getOrNull() ?: return@repeat
            val data = root.optJSONObject("data") ?: return@repeat
            val state = data.optString("state")
            val progress = data.optJSONObject("progress")?.optInt("percent", data.optInt("percent", 0)) ?: data.optInt("percent", 0)
            val message = data.optString("message", "复合字体正在后台生成")
            mixState = mixState.copy(taskState = state.ifBlank { "running" }, message = message, progress = progress.coerceIn(0, 100))
            snapshot = snapshot.copy(taskState = state.ifBlank { "running" }, taskMessage = message)
            if (state == "success" || state == "failed") return data
        }
        error("复合字体任务超时，请查看日志")
    }

    private fun parseSnapshot(raw: String): ModuleSnapshot {
        return try {
            val root = firstJson(raw)
            if (root.optString("status") != "ok") return ModuleSnapshot(loading = false, rootGranted = true, error = root.optString("message", "模块状态读取失败"))
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
            ModuleSnapshot(loading = false, rootGranted = true, error = error.message ?: "模块状态解析失败")
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
