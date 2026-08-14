package io.github.xgl34222220.luoshu.ui.settings

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import io.github.xgl34222220.luoshu.BuildConfig
import io.github.xgl34222220.luoshu.RootShell
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private val Context.systemCenterDataStore by preferencesDataStore(name = "system_center")

internal enum class UpdateChannel(val label: String) {
    STABLE("稳定版"),
    PRERELEASE("预发行版"),
}

internal enum class HealthLevel {
    HEALTHY,
    WARNING,
    ERROR,
}

internal data class ModuleConflict(
    val moduleId: String,
    val moduleName: String,
    val target: String,
    val type: String,
    val fileCount: Int,
)

internal data class SystemHealthSnapshot(
    val loading: Boolean = true,
    val error: String = "",
    val modulePresent: Boolean = false,
    val pendingModulePresent: Boolean = false,
    val moduleVersion: String = "",
    val moduleVersionCode: Int = 0,
    val rootManager: String = "Unknown",
    val androidSdk: Int = 0,
    val activeFont: String = "default",
    val payloadFonts: Int = 0,
    val lockState: String = "idle",
    val engineState: String = "",
    val templateState: String = "",
    val alignmentState: String = "",
    val alignmentMode: String = "",
    val selfMountState: String = "",
    val selfMountBackend: String = "",
    val mountEngine: String = "unknown",
    val cachePending: Boolean = false,
    val rebootRequired: Boolean = false,
    val recentWarnings: Int = 0,
    val recentErrors: Int = 0,
    val conflicts: List<ModuleConflict> = emptyList(),
) {
    val level: HealthLevel
        get() = when {
            error.isNotBlank() || !modulePresent -> HealthLevel.ERROR
            activeFont != "default" && payloadFonts <= 0 -> HealthLevel.ERROR
            lockState == "stale" -> HealthLevel.WARNING
            conflicts.isNotEmpty() || recentErrors > 0 || cachePending -> HealthLevel.WARNING
            alignmentState.isNotBlank() && alignmentState !in setOf("verified", "ready", "ok", "passed") -> HealthLevel.WARNING
            else -> HealthLevel.HEALTHY
        }

    val summary: String
        get() = when (level) {
            HealthLevel.HEALTHY -> "字体引擎状态正常"
            HealthLevel.WARNING -> "发现可处理的兼容性提醒"
            HealthLevel.ERROR -> "发现需要处理的问题"
        }
}

internal data class MaintenanceState(
    val busy: Boolean = false,
    val message: String = "",
    val error: String = "",
)

internal data class OnlineUpdateInfo(
    val loading: Boolean = false,
    val error: String = "",
    val version: String = "",
    val versionCode: Int = 0,
    val zipUrl: String = "",
    val changelogUrl: String = "",
    val sha256: String = "",
    val appUrl: String = "",
    val appSha256: String = "",
) {
    val currentVersionCode: Int get() = BuildConfig.VERSION_CODE / 100
    val available: Boolean get() = versionCode > 0 && zipUrl.isNotBlank()
    val hasUpdate: Boolean get() = available && versionCode > currentVersionCode
}

internal class SystemCenterViewModel(application: Application) : AndroidViewModel(application) {
    private val context = application.applicationContext
    private val channelKey = stringPreferencesKey("update_channel")
    private val healthScript = "/data/adb/modules/LuoShu/system/bin/luoshu-health"

    var health by mutableStateOf(SystemHealthSnapshot())
        private set

    var maintenance by mutableStateOf(MaintenanceState())
        private set

    var updateChannel by mutableStateOf(UpdateChannel.STABLE)
        private set

    var updateInfo by mutableStateOf(OnlineUpdateInfo())
        private set

    private var updateJob: Job? = null

    init {
        viewModelScope.launch {
            val stored = runCatching {
                context.systemCenterDataStore.data.first()[channelKey]
            }.getOrNull()
            updateChannel = runCatching { UpdateChannel.valueOf(stored.orEmpty()) }
                .getOrDefault(UpdateChannel.STABLE)
            checkUpdate()
        }
    }

    fun refreshHealth() {
        if (health.loading && health.moduleVersion.isNotBlank()) return
        health = health.copy(loading = true, error = "")
        viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(healthScript)} report",
                timeoutMs = 25_000L,
            )
            health = if (result.code == 0) {
                runCatching { parseHealthReport(result.stdout) }
                    .getOrElse { error ->
                        SystemHealthSnapshot(loading = false, error = error.message ?: "体检结果解析失败")
                    }
            } else {
                SystemHealthSnapshot(
                    loading = false,
                    error = result.stderr.ifBlank { "无法运行洛书系统体检" },
                )
            }
        }
    }

    fun clearStaleState() {
        if (maintenance.busy) return
        maintenance = MaintenanceState(busy = true, message = "正在清理失效锁与残留 PID…")
        viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(healthScript)} repair-stale",
                timeoutMs = 20_000L,
            )
            maintenance = if (result.code == 0 && result.stdout.lineSequence().any { it == "status=ok" }) {
                val changed = result.stdout.lineSequence()
                    .firstOrNull { it.startsWith("changed=") }
                    ?.substringAfter('=')
                    ?.toIntOrNull()
                    ?: 0
                MaintenanceState(message = if (changed > 0) "已清理 $changed 项失效状态" else "没有发现需要清理的残留状态")
            } else {
                MaintenanceState(error = result.stderr.ifBlank { "残留状态清理失败" })
            }
            refreshHealth()
        }
    }

    fun restoreDefault() {
        if (maintenance.busy) return
        maintenance = MaintenanceState(busy = true, message = "正在准备恢复系统默认字体…")
        viewModelScope.launch {
            val result = RootShell.exec(
                "sh ${RootShell.quote(healthScript)} restore-default",
                timeoutMs = 120_000L,
            )
            val restored = result.code == 0 && result.stdout.lineSequence().any { line ->
                runCatching { JSONObject(line.trim()).optString("status") == "ok" }.getOrDefault(false)
            }
            maintenance = if (restored) {
                MaintenanceState(message = "系统字体恢复任务已完成，请按提示完整重启手机")
            } else {
                MaintenanceState(error = result.stderr.ifBlank { result.stdout.ifBlank { "恢复系统字体失败" } })
            }
            refreshHealth()
        }
    }

    fun selectUpdateChannel(channel: UpdateChannel) {
        if (channel == updateChannel) return
        updateChannel = channel
        updateInfo = OnlineUpdateInfo()
        viewModelScope.launch {
            runCatching {
                context.systemCenterDataStore.edit { preferences ->
                    preferences[channelKey] = channel.name
                }
            }
            checkUpdate()
        }
    }

    fun checkUpdate() {
        val requestedChannel = updateChannel
        updateJob?.cancel()
        updateInfo = updateInfo.copy(loading = true, error = "")
        updateJob = viewModelScope.launch {
            val result = runCatching {
                fetchUpdateInfo(requestedChannel)
            }
            if (requestedChannel != updateChannel) return@launch
            updateInfo = result.getOrElse { error ->
                OnlineUpdateInfo(error = error.message ?: "检查更新失败")
            }
        }
    }

    private suspend fun fetchUpdateInfo(channel: UpdateChannel): OnlineUpdateInfo = withContext(Dispatchers.IO) {
        val file = if (channel == UpdateChannel.PRERELEASE) "update-prerelease.json" else "update.json"
        val metadataUrl = "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/main/$file"
        val root = JSONObject(fetchText(metadataUrl, "application/json"))
        val zipUrl = root.optString("zipUrl").trim()
        val versionCode = root.optInt("versionCode", 0)
        require(versionCode > 0 && zipUrl.startsWith("https://")) { "更新元数据不完整" }

        val appUrl = deriveAppUrl(zipUrl)
        val moduleSha = runCatching { fetchPublishedSha256("$zipUrl.sha256") }.getOrDefault("")
        val appSha = if (appUrl.isNotBlank()) {
            runCatching { fetchPublishedSha256("$appUrl.sha256") }.getOrDefault("")
        } else {
            ""
        }
        OnlineUpdateInfo(
            version = root.optString("version").trim(),
            versionCode = versionCode,
            zipUrl = zipUrl,
            changelogUrl = root.optString("changelog").trim(),
            sha256 = moduleSha,
            appUrl = appUrl,
            appSha256 = appSha,
        )
    }

    private fun fetchText(url: String, accept: String = "text/plain"): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 8_000
            readTimeout = 8_000
            instanceFollowRedirects = true
            requestMethod = "GET"
            setRequestProperty("Accept", accept)
            setRequestProperty("User-Agent", "LuoShu/${BuildConfig.VERSION_NAME}")
            setRequestProperty("Cache-Control", "no-cache")
        }
        try {
            val code = connection.responseCode
            if (code !in 200..299) error("更新服务器返回 HTTP $code")
            return connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun fetchPublishedSha256(url: String): String {
        val value = fetchText(url).trim().split(Regex("\\s+"), limit = 2).firstOrNull().orEmpty().lowercase()
        require(value.matches(Regex("[0-9a-f]{64}"))) { "SHA-256 校验文件无效" }
        return value
    }

    private fun deriveAppUrl(zipUrl: String): String {
        val slash = zipUrl.lastIndexOf('/')
        if (slash <= 0) return ""
        val file = zipUrl.substring(slash + 1)
        if (!file.startsWith("LuoShu-") || !file.endsWith(".zip")) return ""
        val artifact = file.removePrefix("LuoShu-").removeSuffix(".zip")
        return zipUrl.substring(0, slash + 1) + "LuoShu-App-$artifact.apk"
    }
}

internal fun parseHealthReport(raw: String): SystemHealthSnapshot {
    val values = linkedMapOf<String, String>()
    val conflicts = mutableListOf<ModuleConflict>()
    raw.lineSequence().forEach { line ->
        when {
            line.startsWith("conflict=") -> {
                val parts = line.substringAfter('=').split('|', limit = 5)
                if (parts.size == 5) {
                    conflicts += ModuleConflict(
                        moduleId = parts[0],
                        moduleName = parts[1],
                        target = parts[2],
                        type = parts[3],
                        fileCount = parts[4].toIntOrNull() ?: 0,
                    )
                }
            }
            '=' in line -> values[line.substringBefore('=')] = line.substringAfter('=')
        }
    }
    if (values["healthVersion"] != "1") error("不支持的体检结果版本")
    return SystemHealthSnapshot(
        loading = false,
        modulePresent = values.bool("modulePresent"),
        pendingModulePresent = values.bool("pendingModulePresent"),
        moduleVersion = values["moduleVersion"].orEmpty(),
        moduleVersionCode = values.int("moduleVersionCode"),
        rootManager = values["rootManager"].orEmpty().ifBlank { "Unknown" },
        androidSdk = values.int("androidSdk"),
        activeFont = values["activeFont"].orEmpty().ifBlank { "default" },
        payloadFonts = values.int("payloadFonts"),
        lockState = values["lockState"].orEmpty().ifBlank { "idle" },
        engineState = values["engineState"].orEmpty(),
        templateState = values["templateState"].orEmpty(),
        alignmentState = values["alignmentState"].orEmpty(),
        alignmentMode = values["alignmentMode"].orEmpty(),
        selfMountState = values["selfMountState"].orEmpty(),
        selfMountBackend = values["selfMountBackend"].orEmpty(),
        mountEngine = values["mountEngine"].orEmpty().ifBlank { "unknown" },
        cachePending = values.bool("cachePending"),
        rebootRequired = values.bool("rebootRequired"),
        recentWarnings = values.int("recentWarnings"),
        recentErrors = values.int("recentErrors"),
        conflicts = conflicts,
    )
}

private fun Map<String, String>.bool(key: String): Boolean = this[key].equals("true", ignoreCase = true)
private fun Map<String, String>.int(key: String): Int = this[key]?.toIntOrNull() ?: 0
