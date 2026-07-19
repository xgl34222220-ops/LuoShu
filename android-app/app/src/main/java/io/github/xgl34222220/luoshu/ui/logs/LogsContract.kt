package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.LuoShuViewModel

@Immutable
internal data class LogsUiState(
    val content: String = "尚未读取日志",
    val lineCount: Int = 0,
    val errorCount: Int = 0,
    val warningCount: Int = 0,
    val tasks: List<TaskCenterItem> = emptyList(),
    val activeTaskCount: Int = 0,
    val completedTaskCount: Int = 0,
    val failedTaskCount: Int = 0,
    val rebootRequired: Boolean = false,
)

internal data class LogsActions(
    val refresh: () -> Unit,
)

internal fun LuoShuViewModel.toLogsUiState(): LogsUiState {
    val normalized = logs.ifBlank { "尚未读取日志" }
    val lines = normalized.lineSequence().toList()
    val current = buildList {
        if (fontLoading || fontRefreshing) {
            add(
                TaskCenterItem(
                    id = "current-font-scan",
                    kind = TaskKind.SCAN,
                    phase = TaskPhase.RUNNING,
                    title = if (fontRefreshing) "正在更新字体索引" else "正在扫描字体库",
                    message = if (fontRefreshing) "正在检查字体目录变化并更新本地缓存" else "正在读取已导入字体与可用字重",
                    progress = -1,
                    timeLabel = "当前",
                    current = true,
                ),
            )
        } else if (fontError.isNotBlank()) {
            add(
                TaskCenterItem(
                    id = "current-font-scan-error",
                    kind = TaskKind.SCAN,
                    phase = TaskPhase.FAILED,
                    title = "字体扫描失败",
                    message = fontError,
                    progress = 100,
                    timeLabel = "最近",
                    current = true,
                ),
            )
        }

        val snapshotPhase = taskPhaseFor("", snapshot.taskMessage, snapshot.taskState)
        if (snapshot.taskState != "idle" && snapshot.taskType != "none") {
            val kind = taskKindFor(snapshot.taskMessage, snapshot.taskType)
            add(
                TaskCenterItem(
                    id = snapshot.taskId.ifBlank { "current-${snapshot.taskType}" },
                    kind = kind,
                    phase = snapshotPhase,
                    title = taskTitle(kind, snapshotPhase),
                    message = snapshot.taskMessage,
                    progress = snapshot.taskProgress,
                    timeLabel = "当前",
                    current = true,
                ),
            )
        }

        if (mixState.busy && snapshot.taskType != "mix") {
            add(
                TaskCenterItem(
                    id = mixState.taskId.ifBlank { "current-mix" },
                    kind = TaskKind.MIX,
                    phase = taskPhaseFor("", mixState.message, mixState.taskState),
                    title = "字体组合进行中",
                    message = mixState.message,
                    progress = mixState.progress,
                    timeLabel = "当前",
                    current = true,
                ),
            )
        }

        if (operationBusy && snapshot.taskType != "switch") {
            val kind = taskKindFor(operationMessage)
            add(
                TaskCenterItem(
                    id = "current-operation",
                    kind = kind,
                    phase = TaskPhase.RUNNING,
                    title = taskTitle(kind, TaskPhase.RUNNING),
                    message = operationMessage.ifBlank { "正在处理字体任务" },
                    progress = -1,
                    timeLabel = "当前",
                    current = true,
                ),
            )
        } else if (!operationBusy && operationMessage.isNotBlank()) {
            val kind = taskKindFor(operationMessage)
            val phase = taskPhaseFor("", operationMessage)
            add(
                TaskCenterItem(
                    id = "latest-operation-${operationMessage.hashCode()}",
                    kind = kind,
                    phase = phase,
                    title = taskTitle(kind, phase),
                    message = operationMessage,
                    progress = if (phase == TaskPhase.INFO) -1 else 100,
                    timeLabel = "最近",
                    current = true,
                ),
            )
        }

        if (rebootRequired || snapshot.rebootRequired) {
            add(
                TaskCenterItem(
                    id = "waiting-reboot",
                    kind = TaskKind.REBOOT,
                    phase = TaskPhase.WAITING_REBOOT,
                    title = "等待完整重启",
                    message = "字体文件已经准备完成，完整重启手机后全局生效",
                    progress = 100,
                    timeLabel = "待处理",
                    current = true,
                ),
            )
        }
    }
    val tasks = mergeTaskItems(current, parseTaskLogItems(normalized))

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
        tasks = tasks,
        activeTaskCount = tasks.count { it.active },
        completedTaskCount = tasks.count { it.completed },
        failedTaskCount = tasks.count { it.phase == TaskPhase.FAILED },
        rebootRequired = rebootRequired || snapshot.rebootRequired,
    )
}
