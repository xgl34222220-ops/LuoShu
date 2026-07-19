package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.ModuleSnapshot
import io.github.xgl34222220.luoshu.SystemWeightState

@Immutable
data class HomeWeightUiState(
    val loading: Boolean = true,
    val supported: Boolean = false,
    val weight: Int = 400,
    val min: Int = 300,
    val max: Int = 700,
    val step: Int = 10,
    val applying: Boolean = false,
    val message: String = "正在读取系统字体粗细…",
    val error: String = "",
)

@Immutable
data class HomeUiState(
    val loading: Boolean = false,
    val version: String = "检测中…",
    val currentFont: String = "系统默认字体",
    val rootGranted: Boolean = false,
    val rootManager: String = "未授权",
    val moduleInstalled: Boolean = false,
    val mountEngine: String = "未知",
    val taskRunning: Boolean = false,
    val taskTitle: String = "字体引擎等待中",
    val taskMessage: String = "暂无后台字体任务",
    val taskProgress: Int = 0,
    val rebootRequired: Boolean = false,
    val error: String = "",
    val systemWeight: HomeWeightUiState = HomeWeightUiState(),
)

data class HomeActions(
    val refresh: () -> Unit,
    val openFontLibrary: () -> Unit,
    val openFontStudio: () -> Unit,
    val openLogs: () -> Unit,
    val restoreDefault: () -> Unit,
    val reboot: () -> Unit,
    val previewSystemWeight: (Float) -> Unit,
    val resetSystemWeight: () -> Unit,
)

internal fun ModuleSnapshot.toHomeUiState(weight: SystemWeightState): HomeUiState {
    val running = taskState == "running" || taskState == "queued"
    return HomeUiState(
        loading = loading,
        version = version,
        currentFont = activeLabel,
        rootGranted = rootGranted,
        rootManager = rootManager,
        moduleInstalled = installed,
        mountEngine = mountEngine,
        taskRunning = running,
        taskTitle = when {
            running -> "字体任务执行中"
            installed && rootGranted -> "字体引擎已就绪"
            installed -> "模块已连接"
            else -> "正在等待模块连接"
        },
        taskMessage = taskMessage,
        taskProgress = taskProgress,
        rebootRequired = rebootRequired,
        error = error,
        systemWeight = HomeWeightUiState(
            loading = weight.loading,
            supported = weight.supported,
            weight = weight.weight,
            min = weight.min,
            max = weight.max,
            step = weight.step,
            applying = weight.applying,
            message = weight.message,
            error = weight.error,
        ),
    )
}
