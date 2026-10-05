package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.ModuleSnapshot

@Immutable
data class HomeUiState(
    val loading: Boolean = false,
    val statusCached: Boolean = false,
    val version: String = "检测中…",
    val currentFont: String = "系统默认字体",
    val rootGranted: Boolean = false,
    val rootManager: String = "未授权",
    val moduleInstalled: Boolean = false,
    val mountEngine: String = "未知",
    val mountHealthy: Boolean = false,
    val taskRunning: Boolean = false,
    val taskTitle: String = "字体引擎等待中",
    val taskMessage: String = "暂无后台字体任务",
    val taskProgress: Int = 0,
    val rebootRequired: Boolean = false,
    val liveApplied: Boolean = false,
    val error: String = "",
)

@Immutable
data class HomeActions(
    val refresh: () -> Unit,
    val openFontLibrary: () -> Unit,
    val openFontStudio: () -> Unit,
    val openLogs: () -> Unit,
    val openSettings: () -> Unit = {},
    val restoreDefault: () -> Unit,
    val reboot: () -> Unit,
)

internal fun ModuleSnapshot.toHomeUiState(): HomeUiState {
    val running = taskState in setOf("running", "queued", "waiting-cleanup", "cleanup-pending")
    val verifiedConnection = !loading && !statusCached
    return HomeUiState(
        loading = loading || statusCached,
        statusCached = statusCached,
        version = version,
        currentFont = if (statusCached) "$activeLabel（上次记录，正在核实）" else effectiveLabel,
        rootGranted = verifiedConnection && rootGranted,
        rootManager = if (verifiedConnection) rootManager else "核实中…",
        moduleInstalled = verifiedConnection && installed,
        mountEngine = mountEngine,
        mountHealthy = verifiedConnection && installed && mountState != "failed" &&
            (activeFont in setOf("", "default") || rebootRequired || mountState == "mounted"),
        taskRunning = running,
        taskTitle = when {
            taskState in setOf("waiting-cleanup", "cleanup-pending") -> "等待字体任务清理"
            running -> "字体任务执行中"
            statusCached -> "正在核实模块状态"
            loading -> "正在连接字体引擎"
            effectFailed -> "字体未生效"
            installed && rootGranted -> "字体引擎已就绪"
            installed -> "模块已连接"
            else -> "正在等待模块连接"
        },
        taskMessage = when {
            running -> taskMessage
            statusCached -> "已显示上次记录，可以先浏览字体；正在核实当前权限与挂载状态"
            effectFailed -> effectFailureMessage
            else -> taskMessage
        },
        taskProgress = taskProgress,
        rebootRequired = verifiedConnection && rebootRequired,
        liveApplied = verifiedConnection && liveApplied,
        error = error,
    )
}
