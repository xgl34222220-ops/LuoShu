package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.LuoShuViewModel

@Immutable
internal data class LogsUiState(
    val content: String = "尚未读取日志",
    val lineCount: Int = 0,
    val errorCount: Int = 0,
    val warningCount: Int = 0,
    val taskState: String = "idle",
    val taskMessage: String = "暂无后台任务",
    val taskProgress: Int = 0,
)

internal data class LogsActions(
    val refresh: () -> Unit,
)

internal fun LuoShuViewModel.toLogsUiState(): LogsUiState {
    val normalized = logs.ifBlank { "尚未读取日志" }
    val lines = normalized.lineSequence().toList()
    return LogsUiState(
        content = normalized,
        lineCount = lines.count { it.isNotBlank() },
        errorCount = lines.count { line ->
            line.contains("error", ignoreCase = true) ||
                line.contains("failed", ignoreCase = true) ||
                line.contains("失败") ||
                line.contains("错误")
        },
        warningCount = lines.count { line ->
            line.contains("warn", ignoreCase = true) || line.contains("警告")
        },
        taskState = snapshot.taskState,
        taskMessage = snapshot.taskMessage,
        taskProgress = snapshot.taskProgress,
    )
}
