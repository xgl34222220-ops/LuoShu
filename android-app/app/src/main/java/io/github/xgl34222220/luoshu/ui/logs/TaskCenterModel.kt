package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.runtime.Immutable

internal enum class TaskKind(val label: String) {
    SCAN("字体扫描"),
    IMPORT("字体导入"),
    APPLY("字体应用"),
    RESTORE("恢复系统字体"),
    MIX("字体组合"),
    DELETE("删除字体"),
    REBOOT("设备重启"),
    TEMPLATE("原厂槽位检查"),
    // Root/permission prerequisites are guidance, not a task that ran (#250).
    PRECONDITION("运行前提"),
    DIAGNOSTIC("后台任务"),
}

internal enum class TaskPhase(val label: String) {
    QUEUED("等待中"),
    RUNNING("进行中"),
    WAITING_CLEANUP("等待清理"),
    SUCCESS("已完成"),
    FAILED("失败"),
    WAITING_REBOOT("等待重启"),
    WAITING_CONFIRMATION("等待挂载确认"),
    INFO("记录"),
}

@Immutable
internal data class TaskCenterItem(
    val id: String,
    val kind: TaskKind,
    val phase: TaskPhase,
    val title: String,
    val message: String,
    val progress: Int = -1,
    val timeLabel: String = "",
    val current: Boolean = false,
) {
    val active: Boolean
        get() = phase == TaskPhase.QUEUED || phase == TaskPhase.RUNNING || phase == TaskPhase.WAITING_CLEANUP

    val completed: Boolean
        get() = phase == TaskPhase.SUCCESS || phase == TaskPhase.WAITING_REBOOT
}

private val structuredLog = Regex("^\\[([^]]+)]\\s+\\[([^]]+)]\\s+(.*)$")
private val percentPattern = Regex("(?:^|\\D)(\\d{1,3})%(?:\\D|$)")
private val internalMixTelemetry = Regex("^\\[[^]]+]\\s+mix\\s+(?:stage=|start:)", RegexOption.IGNORE_CASE)

// Missing Root / permission notices tell the user what to do first. Their imperative
// wording ("请先…完整重启", "授予 Root 权限") is not evidence that a reboot or any font
// task ran, so they must never become a REBOOT task or a SUCCESS (#250).
private val preconditionMarkers = listOf(
    "未找到 root",
    "授予 root",
    "root 权限",
    "未授予",
    "root 未授权",
    "root 授权",
    "permission denied",
    "su: not found",
    "请先连接洛书模块",
)

// Phrases that contain "完成" but say the opposite of completion.
private val negatedCompletion = Regex("(?:未|尚未|没有|没|未能|无法|不能|请先|需先|需要先|先)完成|完成后")

internal fun isPreconditionNotice(message: String): Boolean {
    val normalized = message.lowercase()
    return preconditionMarkers.any { it in normalized }
}

private fun hasCompletionEvidence(normalized: String): Boolean {
    val stripped = negatedCompletion.replace(normalized, " ")
    return "已完成" in stripped || "完成" in stripped
}

internal fun taskKindFor(message: String, type: String = ""): TaskKind {
    val normalized = "$type $message".lowercase()
    return when {
        type == "mix" -> TaskKind.MIX
        type == "switch" && ("default" in normalized || "恢复" in normalized) -> TaskKind.RESTORE
        type == "switch" || "字体应用失败" in normalized -> TaskKind.APPLY
        isPreconditionNotice(normalized) -> TaskKind.PRECONDITION
        // SERVICE checks may mention a later explicit apply. That wording does
        // not make the background template check a user-requested font apply.
        "原厂字体槽位模板" in normalized || "原厂模板" in normalized -> TaskKind.TEMPLATE
        "复合" in normalized || "组合" in normalized || " mix" in normalized -> TaskKind.MIX
        "应用" in normalized || "切换" in normalized || "switch" in normalized -> TaskKind.APPLY
        "恢复" in normalized || "系统字体" in normalized && "默认" in normalized -> TaskKind.RESTORE
        "导入" in normalized || "import" in normalized || "提取字体" in normalized -> TaskKind.IMPORT
        "删除" in normalized || "delete" in normalized -> TaskKind.DELETE
        "重启" in normalized || "reboot" in normalized -> TaskKind.REBOOT
        "扫描" in normalized || "索引" in normalized || "字体库" in normalized || "fingerprint" in normalized -> TaskKind.SCAN
        else -> TaskKind.DIAGNOSTIC
    }
}

internal fun taskPhaseFor(level: String, message: String, state: String = ""): TaskPhase {
    val normalized = "$state $level $message".lowercase()
    return when {
        // A failed font operation may still own processes. Only its cleanup receipt
        // can remove it from the active count; old success/error wording cannot.
        state == "cleanup-pending" -> TaskPhase.WAITING_CLEANUP
        "failed" in normalized || "error" in normalized || "失败" in normalized || "错误" in normalized -> TaskPhase.FAILED
        // A prerequisite notice without an explicit persisted state is information only.
        state.isBlank() && isPreconditionNotice(normalized) -> TaskPhase.INFO
        "等待主命名空间挂载确认" in normalized -> TaskPhase.WAITING_CONFIRMATION
        "重启后" in normalized || "等待重启" in normalized || "reboot required" in normalized -> TaskPhase.WAITING_REBOOT
        state == "queued" || "queued" in normalized || "排队" in normalized || "等待执行" in normalized -> TaskPhase.QUEUED
        state == "running" || "running" in normalized || "正在" in normalized || "开始" in normalized || "处理中" in normalized -> TaskPhase.RUNNING
        state == "success" || "success" in normalized || "成功" in normalized || hasCompletionEvidence(normalized) -> TaskPhase.SUCCESS
        else -> TaskPhase.INFO
    }
}

internal fun taskTitle(kind: TaskKind, phase: TaskPhase): String = if (kind == TaskKind.PRECONDITION && phase != TaskPhase.FAILED) {
    "运行前提未满足"
} else when (phase) {
    TaskPhase.QUEUED -> "${kind.label}等待执行"
    TaskPhase.RUNNING -> "${kind.label}进行中"
    TaskPhase.WAITING_CLEANUP -> "${kind.label}等待清理"
    TaskPhase.SUCCESS -> "${kind.label}已完成"
    TaskPhase.FAILED -> "${kind.label}失败"
    TaskPhase.WAITING_REBOOT -> "${kind.label}等待重启"
    TaskPhase.WAITING_CONFIRMATION -> "${kind.label}等待挂载确认"
    TaskPhase.INFO -> kind.label
}

internal fun parseTaskLogItems(content: String, limit: Int = 18): List<TaskCenterItem> {
    val candidates = content.lineSequence().mapIndexedNotNull { index, raw ->
        val line = raw.trim()
        if (line.isBlank()) return@mapIndexedNotNull null
        // Stage telemetry describes one mix task. The persisted current task already exposes its
        // latest stage, so treating every telemetry line as a task permanently inflates the active
        // count (for example, nine stages became "9 个任务正在处理").
        if (internalMixTelemetry.containsMatchIn(line)) return@mapIndexedNotNull null
        val match = structuredLog.matchEntire(line)
        val time = match?.groupValues?.getOrNull(1).orEmpty()
        val level = match?.groupValues?.getOrNull(2).orEmpty()
        val message = match?.groupValues?.getOrNull(3)?.trim().orEmpty().ifBlank { line }
        val kind = taskKindFor(message)
        if (kind == TaskKind.DIAGNOSTIC) return@mapIndexedNotNull null
        val phase = taskPhaseFor(level, message)
        val progress = percentPattern.find(message)?.groupValues?.getOrNull(1)?.toIntOrNull()?.coerceIn(0, 100) ?: -1
        TaskCenterItem(
            id = "log-$index-${message.hashCode()}",
            kind = kind,
            phase = phase,
            title = taskTitle(kind, phase),
            message = message,
            progress = progress,
            // Early boot can log before wall-clock synchronization. Do not
            // present the epoch date as a measured reboot completion time.
            timeLabel = if (time.startsWith("1970-")) "开机早期，时间未同步" else time,
        )
    }.toList().asReversed()

    val seen = linkedSetOf<String>()
    return candidates.filter { item ->
        val key = "${item.kind}:${item.phase}:${item.message.lowercase()}"
        seen.add(key)
    }.take(limit)
}

internal fun mergeTaskItems(
    current: List<TaskCenterItem>,
    history: List<TaskCenterItem>,
    limit: Int = 20,
): List<TaskCenterItem> {
    val seen = linkedSetOf<String>()
    return (current + history).filter { item ->
        val key = "${item.kind}:${item.message.lowercase()}"
        seen.add(key)
    }.take(limit)
}
