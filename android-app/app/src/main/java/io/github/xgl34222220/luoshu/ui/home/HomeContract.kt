package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.ModuleSnapshot

@Immutable
data class HomeUiState(
    val loading: Boolean = false,
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
    val running = taskState == "running" || taskState == "queued"
    return HomeUiState(
        loading = loading,
        version = version,
        currentFont = effectiveLabel,
        rootGranted = rootGranted,
        rootManager = rootManager,
        moduleInstalled = installed,
        mountEngine = mountEngine,
        mountHealthy = installed && mountState != "failed" &&
            (activeFont in setOf("", "default") || rebootRequired || mountState == "mounted"),
        taskRunning = running,
        taskTitle = when {
            running -> "字体任务执行中"
            effectFailed -> "字体未生效"
            installed && rootGranted -> "字体引擎已就绪"
            installed -> "模块已连接"
            else -> "正在等待模块连接"
        },
        taskMessage = if (effectFailed) effectFailureMessage else taskMessage,
        taskProgress = taskProgress,
        rebootRequired = rebootRequired,
        error = error,
    )
}
