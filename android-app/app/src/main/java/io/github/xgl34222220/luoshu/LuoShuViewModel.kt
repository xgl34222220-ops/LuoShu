package io.github.xgl34222220.luoshu

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import kotlin.math.roundToInt

internal data class ModuleSnapshot(
    val loading: Boolean = true,
    val rootGranted: Boolean = false,
    val installed: Boolean = false,
    val version: String = "检测中…",
    val versionCode: Int = 0,
    val activeFont: String = "default",
    val effectiveFont: String = "unknown",
    val fontEffectState: String = "unknown",
    val verificationState: String = "unknown",
    val verificationMode: String = "unknown",
    val verificationReason: String = "",
    val mountState: String = "unknown",
    val mountFailure: String = "",
    val taskType: String = "none",
    val taskId: String = "",
    val taskState: String = "idle",
    val taskMessage: String = "暂无后台任务",
    val taskProgress: Int = 0,
    val rebootRequired: Boolean = false,
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

    val effectiveLabel: String
        get() = when {
            activeFont in setOf("", "default") || fontEffectState == "system" -> "系统默认字体"
            fontEffectState == "verified" && effectiveFont == activeFont -> activeLabel
            fontEffectState == "failed" -> "系统默认字体（${activeLabel}未生效）"
            fontEffectState == "pending-reboot" -> "${activeLabel}（等待完整重启）"
            else -> "${activeLabel}（已准备，待本次启动验证）"
        }

    val effectFailed: Boolean
        get() = activeFont !in setOf("", "default") && fontEffectState == "failed"

    val effectFailureMessage: String
        get() = when {
            mountFailure.isNotBlank() -> "自挂载失败（${mountFailure}），已安全回滚到系统字体"
            else -> when (verificationReason) {
                "self-mount-not-visible" -> "开机挂载未完整生效，系统已安全使用默认字体"
                "self-mount-failed" -> "本次启动的原子挂载事务失败，已完整回滚到系统字体"
                "self-mount-invalid-backend" -> "检测到不受支持的挂载后端，洛书没有提交字体负载"
                "self-mount-manifest-missing" -> "本次启动的字体与配置挂载清单缺失，已回滚到系统字体"
                "aligned-manifest-missing" -> "字体负载清单缺失，系统已安全使用默认字体"
                "dynamic-config-overridden" -> "系统动态字体配置覆盖了洛书负载，已安全回到系统字体"
                "dynamic-config-mount-failed" -> "系统动态字体配置挂载失败，已完整回滚到系统字体"
                else -> "开机字体验证失败，系统已安全使用默认字体"
            }
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
    val supportsCjk: Boolean = true,
    val revision: String = "",
) {
    val weightLabel: String
        get() = when {
            variable -> "可变字体"
            weights.isEmpty() -> "单字重"
            else -> weights.joinToString(" · ") { role ->
                when (role) {
                    "thin" -> "极细"
                    "extralight" -> "超细"
                    "light" -> "细体"
                    "regular" -> "常规"
                    "medium" -> "中等"
                    "semibold" -> "半粗"
                    "bold" -> "粗体"
                    "extrabold" -> "特粗"
                    "black" -> "黑体"
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
    val cjkAxes: Map<String, Float> = mapOf("wght" to 400f),
    val latinAxes: Map<String, Float> = mapOf("wght" to 400f),
    val digitAxes: Map<String, Float> = mapOf("wght" to 400f),
    val enabled: Boolean = false,
    val busy: Boolean = false,
    val taskId: String = "",
    val taskState: String = "idle",
    val message: String = "请选择中文、英文和数字字体",
    val progress: Int = 0,
    val error: String = "",
)

internal class LuoShuViewModel(application: Application) : AndroidViewModel(application) {
    private val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"
    private val fontLibrarySource = RootFontLibrarySource()
    private val fontIndexStore = FontIndexStore(application)
    private var watchedTaskId: String = ""
    private var cachedFingerprint: String = ""
    private var fontRequestJob: Job? = null
    private var refreshJob: Job? = null
    private var logsJob: Job? = null
    private var mixConfigJob: Job? = null
    private val foreground = MutableStateFlow(true)
    private var pendingForceRefresh = false
    private var cachedIndex: CachedFontIndex? = null
    private var lastFontCheckAt: Long? = null
    private var fontPollJob: Job? = null
    private var libraryVisible = false
    private var fontGeneration = 0L
    private var fontRequestSequence = 0L
    private val fontIndexWriteMutex = Mutex()

    var snapshot by mutableStateOf(ModuleSnapshot())
        private set

    var logs by mutableStateOf("尚未读取日志")
        private set

    var fonts by mutableStateOf<List<FontItem>>(emptyList())
        private set

    var fontLoading by mutableStateOf(false)
        private set

    var fontRefreshing by mutableStateOf(false)
        private set

    var fontIndexVerified by mutableStateOf(false)
        private set

    var fontCacheReady by mutableStateOf(false)
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

    private val cacheLoadJob = viewModelScope.createFontCacheRestore {
        val cached = withContext(Dispatchers.IO) { fontIndexStore.load() }
        if (cached != null) publishFontIndex(cached, verified = false)
        fontCacheReady = true
    }

    init {
        // Publish the lazy Job field before Main.immediate can execute cache callbacks or
        // refreshFonts(). Cache IO is allowed to return immediately, including an empty cache.
        cacheLoadJob.start()
        refreshFonts()
    }

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

    fun setForeground(visible: Boolean) {
        val resumed = visible && !foreground.value
        foreground.value = visible
        if (!visible) {
            fontPollJob?.cancel()
            fontPollJob = null
            fontRequestJob?.cancel()
        } else {
            if (resumed) {
                lastFontCheckAt = null
                refresh()
                refreshFonts()
            }
            updateFontPolling()
        }
    }

    fun setFontLibraryVisible(visible: Boolean) {
        libraryVisible = visible
        updateFontPolling()
    }

    private fun updateFontPolling() {
        if (!libraryVisible || !foreground.value) {
            fontPollJob?.cancel()
            fontPollJob = null
            return
        }
        if (fontPollJob?.isActive == true) return
        fontPollJob = viewModelScope.launch {
            while (currentCoroutineContext().isActive) {
                ensureFonts()
                delay(30_000L)
            }
        }
    }

    fun refresh() {
        if (refreshJob?.isActive == true) return
        snapshot = snapshot.copy(loading = true, error = "")
        refreshJob = viewModelScope.launch {
            val result = RootShell.exec(
                "if [ -f ${RootShell.quote(bridge)} ]; then sh ${RootShell.quote(bridge)} status; " +
                    "else printf '%s\\n' '{\"status\":\"error\",\"message\":\"请先刷入匹配的洛书模块\"}'; fi",
                timeoutMs = 20_000L,
            )
            if (result.code != 0) {
                snapshot = ModuleSnapshot(
                    loading = false,
                    rootGranted = false,
                    error = result.stderr.ifBlank { "Root 授权失败或 su 不可用" },
                )
                fontIndexVerified = false
                fontError = "Root 权限不可用；当前字体列表尚未核实"
                return@launch
            }
            val parsed = parseSnapshot(result.stdout)
            snapshot = parsed
            rebootRequired = parsed.rebootRequired
            resumePendingTask(parsed)
            if (parsed.installed) ensureFonts()
            else {
                fontIndexVerified = false
                fontError = parsed.error.ifBlank { "模块不可用；当前显示上次保存的字体列表" }
            }
        }
    }

    fun ensureFonts(force: Boolean = false) = refreshFonts(force)

    fun refreshFonts(force: Boolean = false) {
        if (force) {
            fontGeneration += 1
            fontIndexVerified = false
        }
        if (!foreground.value) {
            if (force) pendingForceRefresh = true
            return
        }
        if (fontRequestJob?.isActive == true) {
            if (force) pendingForceRefresh = true
            return
        }
        val forceScan = force || pendingForceRefresh
        val now = System.nanoTime() / 1_000_000L
        // Coalesce startup, navigation and status callbacks without suppressing later checks.
        if (!forceScan && lastFontCheckAt?.let { now - it < 2_000L } == true) return
        pendingForceRefresh = false
        lastFontCheckAt = now
        val generation = fontGeneration
        val request = ++fontRequestSequence
        fontRequestJob = viewModelScope.launch {
            cacheLoadJob.join()
            fontLoading = cachedIndex == null
            fontRefreshing = cachedIndex != null
            fontIndexVerified = false
            fontError = ""
            try {
                val previous = cachedIndex
                val index = loadFontLibrary(previous, forceScan, fontLibrarySource) { value, verified ->
                    if (generation == fontGeneration) publishFontIndex(value, verified)
                }
                if (generation == fontGeneration) {
                    fontError = ""
                    // No fsync for an unchanged index on every navigation/foreground check.
                    if (previous?.fingerprint != index.fingerprint || previous.fonts != index.fonts ||
                        previous.currentFont != index.currentFont
                    ) persistFontIndex(currentFont = index.currentFont)
                }
            } catch (cancelled: CancellationException) {
                if (request == fontRequestSequence) lastFontCheckAt = null
                throw cancelled
            } catch (error: Exception) {
                if (request == fontRequestSequence && generation == fontGeneration) {
                    fontIndexVerified = false
                    fontError = error.message.orEmpty().ifBlank { "字体库核查失败，请检查 Root 与目录权限" } +
                        if (cachedIndex != null) "；当前仅显示未核实的列表，可刷新重试" else ""
                }
            } finally {
                if (request == fontRequestSequence) {
                    fontLoading = false
                    fontRefreshing = false
                    fontRequestJob = null
                    if (pendingForceRefresh && foreground.value && currentCoroutineContext().isActive) {
                        refreshFonts()
                    }
                }
            }
        }
    }

    private fun publishFontIndex(index: CachedFontIndex, verified: Boolean) {
        FontLoadDiagnostics.mark(if (verified) "font_index_verified" else "font_index_visible", index.fonts.size, verified)
        cachedIndex = index
        fonts = index.fonts
        cachedFingerprint = index.fingerprint
        fontIndexVerified = verified
        fontLoading = false
        fontRefreshing = !verified
        // Cached selection is display-only until a live directory check succeeds.
        if (verified) snapshot = snapshot.copy(activeFont = index.currentFont)
        normalizeMixSelections()
    }

    private suspend fun persistFontIndex(currentFont: String = snapshot.activeFont) = fontIndexWriteMutex.withLock {
        val index = CachedFontIndex(
            fingerprint = cachedFingerprint,
            currentFont = currentFont.ifBlank { "default" },
            fonts = fonts,
            savedAt = System.currentTimeMillis(),
        )
        cachedIndex = index
        withContext(Dispatchers.IO) {
            runCatching { fontIndexStore.save(index) }
        }
    }

    fun refreshMixConfig() {
        if (mixState.loading || mixState.busy) return
        mixState = mixState.copy(loading = true, error = "")
        mixConfigJob?.cancel()
        mixConfigJob = viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(bridge)} mix_config",
                timeoutMs = 25_000L,
            )
            try {
                if (result.code != 0) error(result.stderr.ifBlank { "组合配置读取失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "组合配置读取失败"))
                val data = root.getJSONObject("data")
                val cjkWeight = data.optInt("cjkWeight", mixState.cjkWeight).coerceIn(1, 1000)
                val latinWeight = data.optInt("latinWeight", mixState.latinWeight).coerceIn(1, 1000)
                val digitWeight = data.optInt("digitWeight", mixState.digitWeight).coerceIn(1, 1000)
                mixState = mixState.copy(
                    loading = false,
                    enabled = data.optBoolean("enabled", false),
                    cjk = data.optString("cjk", mixState.cjk),
                    latin = data.optString("latin", mixState.latin),
                    digit = data.optString("digit", mixState.digit),
                    cjkWeight = cjkWeight,
                    latinWeight = latinWeight,
                    digitWeight = digitWeight,
                    cjkAxes = parseAxes(data.optString("cjkAxes"), cjkWeight),
                    latinAxes = parseAxes(data.optString("latinAxes"), latinWeight),
                    digitAxes = parseAxes(data.optString("digitAxes"), digitWeight),
                    message = if (data.optBoolean("enabled", false)) "当前正在使用复合字体" else "可直接生成新的复合字体",
                    error = "",
                )
                normalizeMixSelections()
            } catch (error: Throwable) {
                val message = error.message.orEmpty()
                mixState = if (message.contains("interrupted by close", ignoreCase = true)) {
                    mixState.copy(loading = false, error = "")
                } else {
                    mixState.copy(loading = false, error = message.ifBlank { "组合配置读取失败" })
                }
            }
        }
    }

    fun updateMixFont(slot: MixSlot, fontId: String) {
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjk = fontId, cjkAxes = mapOf("wght" to mixState.cjkWeight.toFloat()))
            MixSlot.Latin -> mixState.copy(latin = fontId, latinAxes = mapOf("wght" to mixState.latinWeight.toFloat()))
            MixSlot.Digit -> mixState.copy(digit = fontId, digitAxes = mapOf("wght" to mixState.digitWeight.toFloat()))
        }
    }

    fun updateMixWeight(slot: MixSlot, weight: Int) {
        updateMixAxis(slot, "wght", weight.coerceIn(1, 1000).toFloat())
    }

    fun updateMixAxis(slot: MixSlot, tag: String, value: Float) {
        val cleanTag = tag.trim()
        if (cleanTag.length != 4 || !value.isFinite()) return
        val safe = if (cleanTag == "wght") value.coerceIn(1f, 1000f) else value
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(
                cjkWeight = if (cleanTag == "wght") safe.roundToInt() else mixState.cjkWeight,
                cjkAxes = mixState.cjkAxes + (cleanTag to safe),
            )
            MixSlot.Latin -> mixState.copy(
                latinWeight = if (cleanTag == "wght") safe.roundToInt() else mixState.latinWeight,
                latinAxes = mixState.latinAxes + (cleanTag to safe),
            )
            MixSlot.Digit -> mixState.copy(
                digitWeight = if (cleanTag == "wght") safe.roundToInt() else mixState.digitWeight,
                digitAxes = mixState.digitAxes + (cleanTag to safe),
            )
        }
    }

    fun startMix() {
        if (!fontIndexVerified) {
            mixState = mixState.copy(error = "请先完成字体库核查后再生成组合")
            ensureFonts()
            return
        }
        if (mixState.busy || operationBusy) return
        val cjk = mixState.cjk
        val latin = mixState.latin
        val digit = mixState.digit
        if (cjk.isBlank() || latin.isBlank() || digit.isBlank()) {
            mixState = mixState.copy(error = "请先选择中文、英文和数字字体")
            return
        }

        val cjkAxes = serializeAxes(mixState.cjkAxes, mixState.cjkWeight)
        val latinAxes = serializeAxes(mixState.latinAxes, mixState.latinWeight)
        val digitAxes = serializeAxes(mixState.digitAxes, mixState.digitWeight)
        mixState = mixState.copy(
            busy = true,
            taskState = "queued",
            message = "正在提交复合字体任务…",
            progress = 1,
            error = "",
        )
        viewModelScope.launch {
            try {
                val command = buildString {
                    append("sh ${RootShell.quote(bridge)} mix_start ")
                    append(RootShell.quote(cjk)).append(' ')
                    append(RootShell.quote(latin)).append(' ')
                    append(RootShell.quote(digit)).append(' ')
                    append(RootShell.quote(cjkAxes)).append(' ')
                    append(RootShell.quote(latinAxes)).append(' ')
                    append(RootShell.quote(digitAxes))
                }
                val start = RootShell.exec(command, timeoutMs = 20_000L)
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动复合字体任务" })
                val root = firstJson(start.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "无法启动复合字体任务"))
                val taskId = root.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("复合字体任务 ID 缺失")
                watchMixTask(taskId)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                finishMixFailure(error.message ?: "复合字体生成失败")
            }
        }
    }

    fun applyFont(fontId: String) {
        if (fontId != "default" && !fontLibraryContains(fontIndexVerified, fonts, fontId, requireValid = true)) {
            operationMessage = "字体列表尚未核实，请先刷新字体库"
            ensureFonts()
            return
        }
        if (operationBusy || mixState.busy) return
        operationBusy = true
        operationMessage = if (fontId == "default") "正在准备恢复系统字体…" else "正在验证并应用字体…"
        viewModelScope.launch {
            try {
                if (fontId != "default") {
                    val validation = RootShell.exec(
                        "sh ${RootShell.quote(bridge)} validate ${RootShell.quote(fontId)}",
                        timeoutMs = 35_000L,
                    )
                    if (validation.code != 0) error(validation.stderr.ifBlank { "字体验证失败" })
                    val validationJson = firstJson(validation.stdout)
                    if (validationJson.optString("status") != "ok" ||
                        validationJson.optJSONObject("data")?.optBoolean("valid", true) == false
                    ) {
                        error(
                            validationJson.optString(
                                "message",
                                validationJson.optJSONObject("data")?.optString("error", "字体文件不可用")
                                    ?: "字体文件不可用",
                            ),
                        )
                    }
                }

                val start = RootShell.exec(
                    "sh ${RootShell.quote(bridge)} switch_start ${RootShell.quote(fontId)}",
                    timeoutMs = 20_000L,
                )
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动字体切换" })
                val startJson = firstJson(start.stdout)
                if (startJson.optString("status") != "ok") error(startJson.optString("message", "无法启动字体切换"))
                val taskId = startJson.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("字体任务 ID 缺失")
                watchSwitchTask(taskId, fontId)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体应用失败"
                snapshot = snapshot.copy(taskState = "failed", taskMessage = operationMessage)
                operationBusy = false
            }
        }
    }

    fun deleteFont(fontId: String) {
        if (!fontLibraryContains(fontIndexVerified, fonts, fontId, requireValid = false)) {
            operationMessage = "字体列表尚未核实，请先刷新字体库"
            ensureFonts()
            return
        }
        if (operationBusy || mixState.busy || fontId.isBlank() || fontId == "default") return
        operationBusy = true
        operationMessage = "正在删除字体…"
        viewModelScope.launch {
            try {
                val result = RootShell.exec(
                    "sh ${RootShell.quote(bridge)} delete ${RootShell.quote(fontId)}",
                    timeoutMs = 35_000L,
                )
                if (result.code != 0) error(result.stderr.ifBlank { "字体删除失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "字体删除失败"))
                fontGeneration += 1
                fonts = fonts.filterNot { it.id == fontId }
                cachedFingerprint = ""
                fontIndexVerified = false
                normalizeMixSelections()
                persistFontIndex()
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
        // Complete reboot is deliberately independent from font-task busy state. A stale worker
        // flag used to make the button look dead for tens of seconds even though reboot itself is
        // immediate. The shell bridge backgrounds the reboot command, so use a short request timeout.
        operationMessage = "正在请求完整重启…"
        viewModelScope.launch {
            val result = RootShell.exec("sh ${RootShell.quote(bridge)} reboot", timeoutMs = 4_000L)
            if (result.code != 0) {
                operationMessage = result.stderr.ifBlank { "重启请求失败" }
            }
        }
    }

    fun refreshLogs() {
        if (logsJob?.isActive == true) return
        logsJob = viewModelScope.launch {
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

    private fun resumePendingTask(state: ModuleSnapshot) {
        if (state.taskId.isBlank() || state.taskId == watchedTaskId) return
        when {
            state.taskType == "mix" && state.taskState in setOf("queued", "running") -> {
                mixState = mixState.copy(
                    busy = true,
                    taskId = state.taskId,
                    taskState = state.taskState,
                    message = state.taskMessage,
                    progress = state.taskProgress,
                    error = "",
                )
                viewModelScope.launch { watchMixTask(state.taskId) }
            }
            state.taskType == "switch" && state.taskState in setOf("queued", "running") -> {
                operationBusy = true
                operationMessage = state.taskMessage
                viewModelScope.launch { watchSwitchTask(state.taskId, state.activeFont) }
            }
            state.taskType == "mix" && state.taskState == "success" -> {
                mixState = mixState.copy(
                    busy = false,
                    enabled = state.activeFont == "mix",
                    taskId = state.taskId,
                    taskState = "success",
                    message = state.taskMessage,
                    progress = 100,
                    error = "",
                )
            }
            state.taskState == "failed" -> {
                if (state.taskType == "mix") {
                    mixState = mixState.copy(
                        busy = false,
                        taskId = state.taskId,
                        taskState = "failed",
                        message = state.taskMessage,
                        progress = 100,
                        error = state.taskMessage,
                    )
                } else {
                    operationMessage = state.taskMessage
                }
            }
        }
    }

    private suspend fun watchSwitchTask(taskId: String, fontId: String) {
        if (watchedTaskId == taskId) return
        watchedTaskId = taskId
        operationBusy = true
        try {
            val result = waitForTask("switch_status", taskId, timeoutSeconds = 390) { data ->
                operationMessage = data.optString("message", "正在处理字体…")
                snapshot = snapshot.copy(
                    taskType = "switch",
                    taskId = taskId,
                    taskState = data.optString("state", "running"),
                    taskMessage = operationMessage,
                    taskProgress = data.optInt("percent", snapshot.taskProgress).coerceIn(0, 100),
                )
            }
            if (result.optString("state") != "success") error(result.optString("message", "字体应用失败"))
            val applied = result.optString("font", fontId).ifBlank { fontId }
            val reused = result.optBoolean("reused", false)
            operationMessage = when {
                reused -> "当前字体已验证，无需重新生成或重启"
                applied == "default" -> "已准备恢复系统字体，重启后生效"
                else -> "字体已准备完成，重启后全局生效"
            }
            val nextRebootRequired = if (reused) rebootRequired else true
            rebootRequired = nextRebootRequired
            snapshot = snapshot.copy(
                activeFont = applied,
                taskType = "switch",
                taskId = taskId,
                taskState = "success",
                taskMessage = operationMessage,
                taskProgress = 100,
                rebootRequired = nextRebootRequired,
            )
            persistFontIndex(currentFont = applied)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Throwable) {
            operationMessage = error.message ?: "字体应用失败"
            snapshot = snapshot.copy(taskState = "failed", taskMessage = operationMessage, taskProgress = 100)
        } finally {
            operationBusy = false
            watchedTaskId = ""
        }
    }

    private suspend fun watchMixTask(taskId: String) {
        if (watchedTaskId == taskId) return
        watchedTaskId = taskId
        mixState = mixState.copy(
            busy = true,
            taskId = taskId,
            taskState = "running",
            message = "复合字体正在后台生成",
            error = "",
        )
        try {
            val result = waitForTask("mix_status", taskId, timeoutSeconds = 720) { data ->
                val state = data.optString("state", "running")
                val progress = data.optJSONObject("progress")
                    ?.optInt("percent", data.optInt("percent", 0))
                    ?: data.optInt("percent", 0)
                val message = data.optString("message", "复合字体正在后台生成")
                mixState = mixState.copy(
                    taskId = taskId,
                    taskState = state,
                    message = message,
                    progress = progress.coerceIn(0, 100),
                )
                snapshot = snapshot.copy(
                    taskType = "mix",
                    taskId = taskId,
                    taskState = state,
                    taskMessage = message,
                    taskProgress = progress.coerceIn(0, 100),
                )
            }
            if (result.optString("state") != "success") error(result.optString("message", "复合字体生成失败"))
            val reused = result.optBoolean("reused", false)
            val message = result.optString("message", "复合字体已生成，重启后生效")
            val nextRebootRequired = if (reused) rebootRequired else true
            mixState = mixState.copy(
                busy = false,
                enabled = true,
                taskId = taskId,
                taskState = "success",
                message = message,
                progress = 100,
                error = "",
            )
            rebootRequired = nextRebootRequired
            snapshot = snapshot.copy(
                activeFont = "mix",
                taskType = "mix",
                taskId = taskId,
                taskState = "success",
                taskMessage = message,
                taskProgress = 100,
                rebootRequired = nextRebootRequired,
            )
            persistFontIndex(currentFont = "mix")
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Throwable) {
            finishMixFailure(error.message ?: "复合字体生成失败")
        } finally {
            watchedTaskId = ""
        }
    }

    private suspend fun waitForTask(
        command: String,
        taskId: String,
        timeoutSeconds: Int,
        onProgress: (JSONObject) -> Unit,
    ): JSONObject {
        var failures = 0
        val budget = TaskPollBudget(timeoutSeconds.toLong() * 1_000L)
        while (budget.remainingMs > 0L) {
            awaitForeground(budget)
            val intervalMs = if (budget.elapsedMs < 30_000L) 1_000L else 2_000L
            delay(minOf(intervalMs, budget.remainingMs))
            awaitForeground(budget)
            val remainingMs = budget.remainingMs
            if (remainingMs <= 0L) break
            val status = RootShell.exec(
                "sh ${RootShell.quote(bridge)} $command ${RootShell.quote(taskId)}",
                timeoutMs = minOf(15_000L, remainingMs),
            )
            if (status.code != 0) {
                failures += 1
                if (failures >= 8) error(status.stderr.ifBlank { "连续无法读取任务状态" })
                continue
            }
            val root = runCatching { firstJson(status.stdout) }.getOrNull()
            val data = root?.optJSONObject("data")
            if (root?.optString("status") != "ok" || data == null) {
                failures += 1
                if (failures >= 8) error(root?.optString("message", "任务状态读取失败") ?: "任务状态读取失败")
                continue
            }
            failures = 0
            val advertisedTimeout = data.optInt("timeout", 0)
            if (advertisedTimeout > 0) budget.extendTo((advertisedTimeout.toLong() + 30L) * 1_000L)
            onProgress(data)
            when (data.optString("state")) {
                "success", "failed" -> return data
            }
        }
        error("字体任务超时，请查看日志")
    }

    private suspend fun awaitForeground(budget: TaskPollBudget) {
        if (foreground.value) return
        val pausedAt = System.nanoTime()
        foreground.first { it }
        budget.excludePause((System.nanoTime() - pausedAt) / 1_000_000L)
    }

    private fun finishMixFailure(message: String) {
        mixState = mixState.copy(
            busy = false,
            taskState = "failed",
            message = message,
            error = message,
            progress = 100,
        )
        snapshot = snapshot.copy(taskState = "failed", taskMessage = message, taskProgress = 100)
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
                effectiveFont = data.optString("effectiveActive", "unknown"),
                fontEffectState = data.optString("fontEffectState", "unknown"),
                verificationState = data.optString("verificationState", "unknown"),
                verificationMode = data.optString("verificationMode", "unknown"),
                verificationReason = data.optString("verificationReason", ""),
                mountState = data.optString("mountState", "unknown"),
                mountFailure = data.optString("mountFailure", ""),
                taskType = data.optString("taskType", "none"),
                taskId = data.optString("taskId", ""),
                taskState = data.optString("taskState", "idle"),
                taskMessage = data.optString("taskMessage", "暂无后台任务"),
                taskProgress = data.optInt("taskProgress", 0).coerceIn(0, 100),
                rebootRequired = data.optBoolean("rebootRequired", false),
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

    private fun parseAxes(raw: String, fallbackWeight: Int): Map<String, Float> {
        val axes = linkedMapOf<String, Float>()
        raw.split(',').forEach { item ->
            val parts = item.split('=', limit = 2)
            if (parts.size != 2) return@forEach
            val tag = parts[0].trim()
            val value = parts[1].trim().toFloatOrNull()
            if (tag.length == 4 && value != null && value.isFinite()) axes[tag] = value
        }
        if ("wght" !in axes) axes["wght"] = fallbackWeight.toFloat()
        return axes.toMap()
    }

    private fun serializeAxes(axes: Map<String, Float>, fallbackWeight: Int): String {
        val normalized = axes.filter { (tag, value) -> tag.length == 4 && value.isFinite() }.toMutableMap()
        if ("wght" !in normalized) normalized["wght"] = fallbackWeight.toFloat()
        return normalized.toSortedMap().entries.joinToString(",") { (tag, value) ->
            val number = if (value % 1f == 0f) value.roundToInt().toString() else value.toString().trimEnd('0').trimEnd('.')
            "$tag=$number"
        }
    }

    private fun firstJson(raw: String): JSONObject {
        val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
            ?: error("未收到 JSON 数据")
        return JSONObject(line.trim())
    }
}
