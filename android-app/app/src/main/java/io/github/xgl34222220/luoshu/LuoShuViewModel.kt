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
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToInt

internal data class ModuleSnapshot(
    val loading: Boolean = true,
    val statusCached: Boolean = false,
    val rootGranted: Boolean = false,
    val installed: Boolean = false,
    val version: String = "检测中…",
    val versionCode: Int = 0,
    val activeFont: String = "default",
    val effectiveFont: String = "unknown",
    val fontEffectState: String = "unknown",
    val liveApplied: Boolean = false,
    val activation: String = "unknown",
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
            fontEffectState == "pending-reboot" -> "${activeLabel}（等待完整重启）"
            activeFont in setOf("", "default") || fontEffectState == "system" -> "系统默认字体"
            fontEffectState == "verified" && effectiveFont == activeFont -> activeLabel
            fontEffectState == "live-mounted" && effectiveFont == activeFont -> "${activeLabel}（当前启动已挂载，重启后完整生效）"
            fontEffectState == "failed" -> "系统默认字体（${activeLabel}未生效）"
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

private data class FontFingerprint(
    val value: String,
    val currentFont: String,
)

internal class LuoShuViewModel(application: Application) : AndroidViewModel(application) {
    private val bridge = "/data/adb/modules/LuoShu/common/app_bridge.sh"
    private val fingerprintBridge = "/data/adb/modules/LuoShu/common/font_library_cache.sh"
    private val fontIndexStore = FontIndexStore(application)
    private val moduleSnapshotStore = ModuleSnapshotStore(application)
    private val initialStatusReady = MutableStateFlow(false)
    private var statusReceived = false
    private var fontStateRevision = 0L
    private var fontTaskTerminalConfirmed = false
    private val fontTaskTimings = AppFontTaskTimings.registry
    private var watchedTaskId: String = ""
    private var cachedFingerprint: String = ""
    private var fontRequestJob: Job? = null
    private var refreshJob: Job? = null
    private var logsJob: Job? = null
    private var mixConfigJob: Job? = null
    private val mixConfigLoadGuard = MixConfigLoadGuard()
    private var prewarmJob: Job? = null
    private var fontTaskJob: Job? = null
    private var pendingFontCleanup: Pair<String, String>? = null
    @Volatile private var prewarmCleanupPending = false
    private val prewarmMutex = Mutex()
    private val foreground = MutableStateFlow(true)
    private var pendingForceRefresh = false
    private var prewarmRequested = false

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

    private val cacheLoadJob = viewModelScope.launch {
        val cached = withContext(Dispatchers.IO) { fontIndexStore.load() }
        if (cached != null && cached.fonts.isNotEmpty()) {
            fonts = cached.fonts
            cachedFingerprint = cached.fingerprint
            normalizeMixSelections()
        }
        fontCacheReady = true
    }

    init {
        viewModelScope.launch {
            val cached = withContext(Dispatchers.IO) { moduleSnapshotStore.load() }
            if (cached != null && !statusReceived) snapshot = cached
        }
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
        foreground.value = visible
    }

    fun refresh() {
        if (refreshJob?.isActive == true) return
        // A running observer already owns progress. A delayed home response must not
        // replace its newer apply result or restart an observer for an older task.
        if (fontTaskJob?.isActive == true) return
        snapshot = snapshot.copy(loading = true, error = "")
        refreshJob = viewModelScope.launch {
            try {
                if (!retryKnownFontCleanup()) return@launch
                val requestedRevision = fontStateRevision
                val result = RootShell.exec(
                    "if [ -f ${RootShell.quote(bridge)} ]; then sh ${RootShell.quote(bridge)} status; " +
                        "else printf '%s\\n' '{\"status\":\"error\",\"message\":\"请先刷入匹配的洛书模块\"}'; fi",
                    timeoutMs = 20_000L,
                )
                if (requestedRevision != fontStateRevision || fontTaskJob?.isActive == true) return@launch
                if (result.code != 0) {
                    statusReceived = true
                    snapshot = ModuleSnapshot(
                        loading = false,
                        rootGranted = false,
                        error = result.stderr.ifBlank { "Root 授权失败或 su 不可用" },
                    )
                    persistModuleDisplay()
                    return@launch
                }
                val parsed = parseSnapshot(result.stdout)
                statusReceived = true
                snapshot = parsed
                rebootRequired = parsed.rebootRequired
                resumePendingTask(parsed)
                persistModuleDisplay()
            } finally {
                initialStatusReady.value = true
            }
        }
    }

    fun ensureFonts(force: Boolean = false) {
        if (force) {
            refreshFonts(force = true)
            return
        }
        requestFontPrewarm()
    }

    fun refreshFonts(force: Boolean = false) {
        if (fontRequestJob?.isActive == true) {
            if (force) pendingForceRefresh = true
            return
        }
        launchFontWork(force = force, showErrors = force)
    }

    private fun requestFontPrewarm() {
        if (prewarmRequested && fonts.isNotEmpty()) return
        prewarmRequested = true
        if (fontRequestJob?.isActive == true) return
        launchFontWork(force = false, showErrors = false)
    }

    private fun launchFontWork(force: Boolean, showErrors: Boolean) {
        fontRequestJob = viewModelScope.launch {
            try {
                cacheLoadJob.join()
                initialStatusReady.first { it }
                if (!snapshot.installed || !snapshot.rootGranted) return@launch
                val hadFonts = fonts.isNotEmpty()
                fontLoading = !hadFonts
                fontRefreshing = hadFonts
                if (showErrors) fontError = ""
                when {
                    force -> rebuildFontIndex(showErrors = true)
                    fonts.isEmpty() -> rebuildFontIndex(showErrors = showErrors)
                    else -> refreshOnlyWhenChanged(showErrors = showErrors)
                }
            } finally {
                fontLoading = false
                fontRefreshing = false
                fontRequestJob = null
                val runPendingRefresh = pendingForceRefresh
                pendingForceRefresh = false
                if (runPendingRefresh && currentCoroutineContext().isActive && snapshot.installed && snapshot.rootGranted) {
                    refreshFonts(force = true)
                }
            }
        }
    }

    private suspend fun refreshOnlyWhenChanged(showErrors: Boolean) {
        val requestedRevision = fontStateRevision
        val fingerprint = readFontFingerprint()
        if (fingerprint == null) {
            if (showErrors) fontError = "无法检查字体目录变化，已继续使用本地索引"
            return
        }
        if (fingerprint.currentFont.isNotBlank() && requestedRevision == fontStateRevision && !operationBusy && !mixState.busy) {
            snapshot = snapshot.copy(activeFont = fingerprint.currentFont)
        }
        if (fingerprint.value.isNotBlank() && fingerprint.value == cachedFingerprint) {
            persistFontIndex()
            return
        }
        rebuildFontIndex(
            showErrors = showErrors,
            knownFingerprint = fingerprint,
        )
    }

    private suspend fun rebuildFontIndex(
        showErrors: Boolean,
        knownFingerprint: FontFingerprint? = null,
    ) {
        val requestedRevision = fontStateRevision
        val suffix = if (knownFingerprint != null || fonts.isNotEmpty()) " refresh" else ""
        val result = RootShell.exec(
            "sh ${RootShell.quote(bridge)} fonts$suffix",
            timeoutMs = 60_000L,
        )
        if (result.code != 0) {
            if (fonts.isEmpty() || showErrors) {
                fontError = result.stderr.ifBlank { "字体库读取失败" }
            }
            return
        }
        try {
            val fallbackCurrent = knownFingerprint?.currentFont ?: snapshot.activeFont
            val (parsedFonts, current) = withContext(Dispatchers.IO) {
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "字体库读取失败"))
                val data = root.getJSONObject("data")
                parseFonts(data.optJSONArray("fonts") ?: JSONArray()) to data.optString("current", fallbackCurrent)
            }
            val fingerprint = knownFingerprint ?: readFontFingerprint()
            if (requestedRevision == fontStateRevision && !operationBusy && !mixState.busy) {
                snapshot = snapshot.copy(activeFont = current)
            }
            fonts = parsedFonts
            cachedFingerprint = fingerprint?.value.orEmpty()
            normalizeMixSelections()
            persistFontIndex()
            fontError = ""
        } catch (error: Throwable) {
            if (fonts.isEmpty() || showErrors) {
                fontError = error.message ?: "字体库解析失败"
            }
        }
    }

    private suspend fun readFontFingerprint(): FontFingerprint? {
        val result = RootShell.exec(
            "if [ -f ${RootShell.quote(fingerprintBridge)} ]; then " +
                "sh ${RootShell.quote(fingerprintBridge)} fingerprint; else exit 127; fi",
            timeoutMs = 8_000L,
        )
        if (result.code != 0) return null
        return runCatching {
            val root = firstJson(result.stdout)
            if (root.optString("status") != "ok") return@runCatching null
            val data = root.optJSONObject("data") ?: return@runCatching null
            FontFingerprint(
                value = data.optString("fingerprint", ""),
                currentFont = data.optString("current", snapshot.activeFont),
            )
        }.getOrNull()
    }

    private suspend fun persistFontIndex(currentFont: String = snapshot.activeFont) {
        val index = CachedFontIndex(
            fingerprint = cachedFingerprint,
            currentFont = currentFont.ifBlank { "default" },
            fonts = fonts,
            savedAt = System.currentTimeMillis(),
        )
        withContext(Dispatchers.IO) {
            runCatching { fontIndexStore.save(index) }
        }
    }

    private suspend fun persistModuleDisplay() {
        val display = snapshot
        withContext(Dispatchers.IO) { runCatching { moduleSnapshotStore.save(display) } }
    }

    private fun moduleReadyForFontOperation(): Boolean {
        if (snapshot.loading || snapshot.statusCached || !snapshot.installed || !snapshot.rootGranted) {
            operationMessage = if (snapshot.loading) "正在核实模块状态，请稍候…" else "请先连接洛书模块并授予 Root 权限"
            return false
        }
        return true
    }

    fun ensureMixConfig() = loadMixConfig(force = false)

    fun refreshMixConfig() = loadMixConfig(force = true)

    private fun loadMixConfig(force: Boolean) {
        if (mixState.busy || operationBusy) return
        val request = mixConfigLoadGuard.begin(force) ?: return
        val requestedFontRevision = fontStateRevision
        mixState = mixState.copy(loading = true, error = "")
        mixConfigJob = viewModelScope.launch {
            try {
                cacheLoadJob.join()
                initialStatusReady.first { it }
                val result = RootShell.exec(
                    "sh ${RootShell.quote(bridge)} mix_config",
                    timeoutMs = 25_000L,
                )
                if (result.code != 0) error(result.stderr.ifBlank { "组合配置读取失败" })
                val root = firstJson(result.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "组合配置读取失败"))
                val data = root.getJSONObject("data")
                val cjkWeight = data.optInt("cjkWeight", mixState.cjkWeight).coerceIn(1, 1000)
                val latinWeight = data.optInt("latinWeight", mixState.latinWeight).coerceIn(1, 1000)
                val digitWeight = data.optInt("digitWeight", mixState.digitWeight).coerceIn(1, 1000)
                val loaded = mixState.copy(
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
                if (mixConfigLoadGuard.complete(
                        request,
                        allowApply = requestedFontRevision == fontStateRevision && !mixState.busy && !operationBusy,
                    )) {
                    mixState = loaded
                    normalizeMixSelections()
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                val message = error.message.orEmpty()
                mixState = if (message.contains("interrupted by close", ignoreCase = true)) {
                    mixState.copy(loading = false, error = "")
                } else {
                    mixState.copy(loading = false, error = message.ifBlank { "组合配置读取失败" })
                }
            } finally {
                mixConfigLoadGuard.failed(request)
                mixState = mixState.copy(loading = false)
                mixConfigJob = null
            }
        }
    }

    fun updateMixFont(slot: MixSlot, fontId: String) {
        val updated = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjk = fontId, cjkAxes = mapOf("wght" to mixState.cjkWeight.toFloat()))
            MixSlot.Latin -> mixState.copy(latin = fontId, latinAxes = mapOf("wght" to mixState.latinWeight.toFloat()))
            MixSlot.Digit -> mixState.copy(digit = fontId, digitAxes = mapOf("wght" to mixState.digitWeight.toFloat()))
        }
        if (updated != mixState) mixConfigLoadGuard.edited()
        mixState = updated
    }

    fun updateMixWeight(slot: MixSlot, weight: Int) {
        updateMixAxis(slot, "wght", weight.coerceIn(1, 1000).toFloat())
    }

    fun updateMixAxis(slot: MixSlot, tag: String, value: Float) {
        val cleanTag = tag.trim()
        if (cleanTag.length != 4 || !value.isFinite()) return
        val safe = if (cleanTag == "wght") value.coerceIn(1f, 1000f) else value
        val updated = when (slot) {
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
        if (updated != mixState) mixConfigLoadGuard.edited()
        mixState = updated
    }

    fun startMix() {
        if (mixState.busy || operationBusy) return
        if (!moduleReadyForFontOperation()) {
            mixState = mixState.copy(error = operationMessage)
            return
        }
        fontStateRevision += 1L
        fontTaskTerminalConfirmed = false
        val cjk = mixState.cjk
        val latin = mixState.latin
        val digit = mixState.digit
        if (cjk.isBlank() || latin.isBlank() || digit.isBlank()) {
            mixState = mixState.copy(error = "请先选择中文、英文和数字字体")
            return
        }

        val timing = fontTaskTimings.begin(FontTaskOperation.MIX)
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
        fontTaskJob = viewModelScope.launch {
            try {
                stopPrewarmWork()
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
                start.requireCleaned()
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动复合字体任务" })
                val root = firstJson(start.stdout)
                if (root.optString("status") != "ok") error(root.optString("message", "无法启动复合字体任务"))
                val taskId = root.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("复合字体任务 ID 缺失")
                fontTaskTimings.bind(timing, FontTaskOperation.MIX, taskId)
                watchMixTask(taskId, requestTiming = timing)
            } catch (cancelled: CancellationException) {
                fontTaskTimings.stopped(timing, cancelled = true, cleanupPending = cancelled.cleanupUnconfirmed())
                if (cancelled.cleanupUnconfirmed()) {
                    mixState = mixState.copy(busy = true, taskState = "cleanup-pending", message = "字体任务清理尚未确认，请查看日志")
                } else if (mixState.taskState != "cleanup-pending") {
                    mixState = mixState.copy(busy = false, taskState = "cancelled", message = "字体任务已取消", error = "")
                }
                throw cancelled
            } catch (error: Throwable) {
                fontTaskTimings.stopped(timing, cancelled = false, cleanupPending = error.cleanupUnconfirmed())
                if (error.cleanupUnconfirmed()) {
                    mixState = mixState.copy(busy = true, taskState = "cleanup-pending", message = error.message ?: "字体任务清理尚未确认")
                } else {
                    finishMixFailure(error.message ?: "复合字体生成失败")
                }
            }
        }.also { job ->
            // Includes cancellation before the launch body gets its first turn.
            job.invokeOnCompletion { cause ->
                fontTaskTimings.stopped(timing, cancelled = cause is CancellationException,
                    cleanupPending = cause?.cleanupUnconfirmed() == true)
            }
        }
    }

    fun prewarmFont(fontId: String) {
        if (fontId.isBlank() || fontId == "default" || !snapshot.installed || operationBusy || mixState.busy) return
        val previous = prewarmJob
        previous?.cancel()
        prewarmJob = viewModelScope.launch(Dispatchers.IO) {
            prewarmMutex.withLock {
                try {
                    // The mutex also covers older requests if an intermediate queued job
                    // was cancelled before it could finish joining its predecessor.
                    previous?.cancelAndJoin()
                    if (prewarmCleanupPending) return@withLock
                    val result = RootShell.exec(
                        "sh ${RootShell.quote(bridge)} prewarm ${RootShell.quote(fontId)}",
                        timeoutMs = 6_000L,
                    )
                    result.requireCleaned()
                } catch (cancelled: CancellationException) {
                    if (cancelled.cleanupUnconfirmed()) prewarmCleanupPending = true
                    throw cancelled
                } catch (error: Exception) {
                    if (error.cleanupUnconfirmed()) prewarmCleanupPending = true
                    // Prewarming is optional; the explicit apply path still validates the font.
                }
            }
        }
    }

    private suspend fun stopPrewarmWork() {
        prewarmJob?.cancelAndJoin()
        prewarmMutex.withLock {
            if (prewarmCleanupPending) throw OwnedTaskCleanupFailure("上一字体预热任务清理尚未确认")
        }
    }

    fun cancelFontTask() {
        if (!canCancelFontTask(fontTaskJob?.isActive == true, fontTaskTerminalConfirmed)) return
        operationMessage = "正在取消字体任务并清理后台进程…"
        if (mixState.busy) mixState = mixState.copy(message = operationMessage)
        fontTaskJob?.cancel(CancellationException("用户取消字体任务"))
    }

    private suspend fun retryKnownFontCleanup(): Boolean {
        val pending = pendingFontCleanup ?: return true
        val (type, taskId) = pending
        val command = if (type == "mix") "font-mix-cancel" else "font-switch-cancel"
        val result = RootShell.exec("sh ${RootShell.quote(bridge)} $command ${RootShell.quote(taskId)}", timeoutMs = 20_000L)
        if (!cleanupConfirmed(result, "task", taskId)) {
            val message = "字体任务清理尚未确认，请查看日志"
            snapshot = snapshot.copy(loading = false, taskState = "cleanup-pending", taskMessage = message, error = message)
            if (type == "mix") mixState = mixState.copy(busy = true, taskState = "cleanup-pending", message = message)
            else { operationBusy = true; operationMessage = message }
            return false
        }
        fontTaskTimings.cleanup(if (type == "mix") FontTaskOperation.MIX else FontTaskOperation.SWITCH, taskId, confirmed = true)
        if (pendingFontCleanup == pending) pendingFontCleanup = null
        if (type == "mix") mixState = mixState.copy(busy = false, taskState = "cancelled", message = "后台字体任务已清理", error = "")
        else operationBusy = false
        return true
    }

    private fun rememberCleanupResult(type: String, taskId: String, cleaned: Boolean) {
        fontTaskTimings.cleanup(if (type == "mix") FontTaskOperation.MIX else FontTaskOperation.SWITCH, taskId, confirmed = cleaned)
        val identity = type to taskId
        if (!cleaned) pendingFontCleanup = identity
        else if (pendingFontCleanup == identity) pendingFontCleanup = null
    }

    fun applyFont(fontId: String) {
        if (operationBusy || mixState.busy) return
        if (!moduleReadyForFontOperation()) return
        val timing = fontTaskTimings.begin(FontTaskOperation.SWITCH)
        fontStateRevision += 1L
        fontTaskTerminalConfirmed = false
        operationBusy = true
        operationMessage = if (fontId == "default") "正在准备恢复系统字体…" else "正在验证并应用字体…"
        fontTaskJob = viewModelScope.launch {
            try {
                stopPrewarmWork()
                if (fontId != "default") {
                    val validation = RootShell.exec(
                        "sh ${RootShell.quote(bridge)} validate ${RootShell.quote(fontId)}",
                        timeoutMs = 35_000L,
                    )
                    validation.requireCleaned()
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
                start.requireCleaned()
                if (start.code != 0) error(start.stderr.ifBlank { "无法启动字体切换" })
                val startJson = firstJson(start.stdout)
                if (startJson.optString("status") != "ok") error(startJson.optString("message", "无法启动字体切换"))
                val taskId = startJson.optJSONObject("data")?.optString("task").orEmpty()
                if (taskId.isBlank()) error("字体任务 ID 缺失")
                fontTaskTimings.bind(timing, FontTaskOperation.SWITCH, taskId)
                watchSwitchTask(taskId, fontId, requestTiming = timing)
            } catch (cancelled: CancellationException) {
                fontTaskTimings.stopped(timing, cancelled = true, cleanupPending = cancelled.cleanupUnconfirmed())
                if (cancelled.cleanupUnconfirmed()) {
                    operationBusy = true
                    operationMessage = "字体任务清理尚未确认，请查看日志"
                    snapshot = snapshot.copy(taskState = "cleanup-pending", taskMessage = operationMessage)
                } else if (snapshot.taskState != "cleanup-pending") {
                    operationBusy = false
                    operationMessage = "字体任务已取消"
                    snapshot = snapshot.copy(taskState = "cancelled", taskMessage = operationMessage)
                }
                throw cancelled
            } catch (error: Throwable) {
                fontTaskTimings.stopped(timing, cancelled = false, cleanupPending = error.cleanupUnconfirmed())
                operationMessage = error.message ?: "字体应用失败"
                operationBusy = error.cleanupUnconfirmed()
                snapshot = snapshot.copy(taskState = if (operationBusy) "cleanup-pending" else "failed", taskMessage = operationMessage)
            }
        }.also { job ->
            // Includes cancellation before the launch body gets its first turn.
            job.invokeOnCompletion { cause ->
                fontTaskTimings.stopped(timing, cancelled = cause is CancellationException,
                    cleanupPending = cause?.cleanupUnconfirmed() == true)
            }
        }
    }

    fun deleteFont(fontId: String) {
        if (operationBusy || mixState.busy || fontId.isBlank() || fontId == "default") return
        if (!moduleReadyForFontOperation()) return
        fontStateRevision += 1L
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
                fonts = fonts.filterNot { it.id == fontId }
                cachedFingerprint = ""
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
        val timingOperation = when (state.taskType) {
            "switch" -> FontTaskOperation.SWITCH
            "mix" -> FontTaskOperation.MIX
            else -> null
        }
        if (timingOperation != null) {
            val timing = fontTaskTimings.attach(timingOperation, state.taskId)
            fontTaskTimings.observe(timing, timingOperation, state.taskId, state.taskState)
            if (state.taskState in setOf("cleanup-pending", "waiting-cleanup")) {
                fontTaskTimings.cleanup(timingOperation, state.taskId, confirmed = false)
            }
        }
        if (state.taskType in setOf("switch", "mix") && state.taskState in setOf("cleanup-pending", "waiting-cleanup")) {
            pendingFontCleanup = state.taskType to state.taskId
            if (state.taskType == "mix") {
                mixState = mixState.copy(busy = true, taskId = state.taskId, taskState = "cleanup-pending", message = state.taskMessage)
            } else {
                operationBusy = true
                operationMessage = state.taskMessage
            }
            return
        }
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
                fontTaskJob = viewModelScope.launch { watchMixTask(state.taskId) }
            }
            state.taskType == "switch" && state.taskState in setOf("queued", "running") -> {
                operationBusy = true
                operationMessage = state.taskMessage
                fontTaskJob = viewModelScope.launch { watchSwitchTask(state.taskId, state.activeFont) }
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

    private suspend fun watchSwitchTask(taskId: String, fontId: String, requestTiming: FontTaskRequest? = null) {
        if (watchedTaskId == taskId) return
        val timing = requestTiming ?: fontTaskTimings.attach(FontTaskOperation.SWITCH, taskId)
        watchedTaskId = taskId
        fontTaskTerminalConfirmed = false
        operationBusy = true
        var cleanupPending = false
        try {
            val result = awaitOwnedFontTask(
                taskId = taskId,
                cancelCommand = "sh ${RootShell.quote(bridge)} font-switch-cancel ${RootShell.quote(taskId)}",
                onCleanup = { cleaned, _ ->
                    cleanupPending = !cleaned
                    rememberCleanupResult("switch", taskId, cleaned)
                    if (!cleaned) operationMessage = "字体任务清理尚未确认，请查看日志"
                },
            ) {
                waitForTask("switch_status", taskId, timeoutSeconds = 390) { data ->
                    fontTaskTimings.observe(timing, FontTaskOperation.SWITCH, data.optString("task"), data.optString("state"))
                    operationMessage = data.optString("message", "正在处理字体…")
                    snapshot = snapshot.copy(
                        taskType = "switch",
                        taskId = taskId,
                        taskState = data.optString("state", "running"),
                        taskMessage = operationMessage,
                        taskProgress = data.optInt("percent", snapshot.taskProgress).coerceIn(0, 100),
                    )
                }.also {
                    if (it.optString("state") != "success") error(it.optString("message", "字体应用失败"))
                }
            }
            fontTaskTerminalConfirmed = true
            val applied = result.optString("font", fontId).ifBlank { fontId }
            val reused = result.optBoolean("reused", false)
            val liveApplied = result.optBoolean("liveApplied", reused && snapshot.liveApplied)
            operationMessage = when {
                liveApplied && applied == "default" -> "当前启动已恢复系统字体，重启后完整生效"
                liveApplied -> "当前启动已挂载新字体，重启后完整生效；可继续切换字体"
                reused -> "当前字体与已准备负载一致，可继续切换字体"
                applied == "default" -> "已准备恢复系统字体，完整重启后生效"
                else -> "字体已准备完成，完整重启后生效；可继续切换字体"
            }
            val nextRebootRequired = result.optBoolean("rebootRequired", if (reused) rebootRequired else true)
            rebootRequired = nextRebootRequired
            snapshot = snapshot.copy(
                activeFont = applied,
                effectiveFont = if (liveApplied) applied else if (reused) snapshot.effectiveFont else "unknown",
                fontEffectState = if (liveApplied) {
                    if (applied == "default") "system" else "live-mounted"
                } else if (reused) snapshot.fontEffectState else "pending-reboot",
                liveApplied = liveApplied,
                activation = result.optString("activation", if (liveApplied) "live-mounted" else "pending-reboot"),
                mountState = if (liveApplied) {
                    if (applied == "default") "idle" else "mounted"
                } else snapshot.mountState,
                mountFailure = if (liveApplied) "" else snapshot.mountFailure,
                taskType = "switch",
                taskId = taskId,
                taskState = "success",
                taskMessage = operationMessage,
                taskProgress = 100,
                rebootRequired = nextRebootRequired,
            )
            persistFontIndex(currentFont = applied)
            persistModuleDisplay()
        } catch (cancelled: CancellationException) {
            fontTaskTimings.stopped(timing, cancelled = true, cleanupPending = cleanupPending)
            if (!cleanupPending) {
                operationMessage = "字体任务已取消，后台进程已清理"
                snapshot = snapshot.copy(taskState = "cancelled", taskMessage = operationMessage)
            }
            throw cancelled
        } catch (error: Throwable) {
            fontTaskTimings.stopped(timing, cancelled = false, cleanupPending = cleanupPending)
            if (!cleanupPending) operationMessage = error.message ?: "字体应用失败"
            snapshot = snapshot.copy(taskState = if (cleanupPending) "cleanup-pending" else "failed", taskMessage = operationMessage, taskProgress = 100)
        } finally {
            operationBusy = cleanupPending
            if (cleanupPending) snapshot = snapshot.copy(taskState = "cleanup-pending", taskMessage = operationMessage)
            watchedTaskId = ""
        }
    }

    private suspend fun watchMixTask(taskId: String, requestTiming: FontTaskRequest? = null) {
        if (watchedTaskId == taskId) return
        val timing = requestTiming ?: fontTaskTimings.attach(FontTaskOperation.MIX, taskId)
        watchedTaskId = taskId
        fontTaskTerminalConfirmed = false
        mixState = mixState.copy(
            busy = true,
            taskId = taskId,
            taskState = "running",
            message = "复合字体正在后台生成",
            error = "",
        )
        var cleanupPending = false
        try {
            val result = awaitOwnedFontTask(
                taskId = taskId,
                cancelCommand = "sh ${RootShell.quote(bridge)} font-mix-cancel ${RootShell.quote(taskId)}",
                onCleanup = { cleaned, _ ->
                    cleanupPending = !cleaned
                    rememberCleanupResult("mix", taskId, cleaned)
                    if (!cleaned) mixState = mixState.copy(
                        taskState = "cleanup-pending", message = "字体任务清理尚未确认，请查看日志", error = "后台任务尚未完成清理",
                    )
                },
            ) {
                waitForTask("mix_status", taskId, timeoutSeconds = 720) { data ->
                    fontTaskTimings.observe(timing, FontTaskOperation.MIX, data.optString("task"), data.optString("state"))
                    val state = data.optString("state", "running")
                    val progress = data.optJSONObject("progress")
                        ?.optInt("percent", data.optInt("percent", 0))
                        ?: data.optInt("percent", 0)
                    val message = data.optString("message", "复合字体正在后台生成")
                    mixState = mixState.copy(taskId = taskId, taskState = state, message = message, progress = progress.coerceIn(0, 100))
                    snapshot = snapshot.copy(
                        taskType = "mix", taskId = taskId, taskState = state, taskMessage = message, taskProgress = progress.coerceIn(0, 100),
                    )
                }.also {
                    if (it.optString("state") != "success") error(it.optString("message", "复合字体生成失败"))
                }
            }
            fontTaskTerminalConfirmed = true
            val reused = result.optBoolean("reused", false)
            val liveApplied = result.optBoolean("liveApplied", reused && snapshot.liveApplied)
            val message = when {
                liveApplied -> "当前启动已挂载新组合，重启后完整生效；可继续切换字体"
                reused -> "当前组合与已准备负载一致，可继续切换字体"
                else -> result.optString("message", "复合字体已生成，完整重启后生效")
            }
            val nextRebootRequired = result.optBoolean("rebootRequired", if (reused) rebootRequired else true)
            mixState = mixState.copy(
                busy = true,
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
                effectiveFont = if (liveApplied) "mix" else if (reused) snapshot.effectiveFont else "unknown",
                fontEffectState = if (liveApplied) "live-mounted" else if (reused) snapshot.fontEffectState else "pending-reboot",
                liveApplied = liveApplied,
                activation = result.optString("activation", if (liveApplied) "live-mounted" else "pending-reboot"),
                mountState = if (liveApplied) "mounted" else snapshot.mountState,
                mountFailure = if (liveApplied) "" else snapshot.mountFailure,
                taskType = "mix",
                taskId = taskId,
                taskState = "success",
                taskMessage = message,
                taskProgress = 100,
                rebootRequired = nextRebootRequired,
            )
            persistFontIndex(currentFont = "mix")
            persistModuleDisplay()
        } catch (cancelled: CancellationException) {
            fontTaskTimings.stopped(timing, cancelled = true, cleanupPending = cleanupPending)
            if (!cleanupPending) mixState = mixState.copy(busy = false, taskState = "cancelled", message = "字体任务已取消，后台进程已清理", error = "")
            throw cancelled
        } catch (error: Throwable) {
            fontTaskTimings.stopped(timing, cancelled = false, cleanupPending = cleanupPending)
            if (!cleanupPending) finishMixFailure(error.message ?: "复合字体生成失败")
        } finally {
            if (cleanupPending) mixState = mixState.copy(busy = true, taskState = "cleanup-pending")
            else if (mixState.taskState == "success") mixState = mixState.copy(busy = false)
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
                "success", "failed", "cancelled" -> return data
                "cleanup-pending", "waiting-cleanup" -> error(data.optString("message", "字体任务清理尚未确认，请刷新重试"))
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
                liveApplied = data.optBoolean("liveApplied", false),
                activation = data.optString("activation", "unknown"),
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

    private fun parseFonts(array: JSONArray): List<FontItem> = buildList {
        for (index in 0 until array.length()) {
            val item = array.optJSONObject(index) ?: continue
            val id = item.optString("id")
            if (id.isBlank() || id == "default") continue
            val weightsArray = item.optJSONArray("weights")
            val weights = buildList {
                if (weightsArray != null) {
                    for (weightIndex in 0 until weightsArray.length()) {
                        weightsArray.optString(weightIndex).takeIf { it.isNotBlank() }?.let(::add)
                    }
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
                    supportsCjk = item.optBoolean("supportsCjk", true),
                ),
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

internal fun canCancelFontTask(jobActive: Boolean, terminalConfirmed: Boolean): Boolean =
    jobActive && !terminalConfirmed
