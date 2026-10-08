package io.github.xgl34222220.luoshu

import android.os.SystemClock
import java.util.UUID

internal enum class FontTaskOperation(val value: String) { SWITCH("switch"), MIX("mix") }
internal enum class FontTaskOrigin(val value: String) { APP_REQUEST("app-request"), RECOVERED("recovered") }
internal enum class FontTaskObserver(val value: String) { WAITING("waiting"), TERMINAL("terminal"), FAILED("failed"), CANCELLED("cancelled") }
internal enum class FontTaskCleanup(val value: String) { NONE("none"), PENDING("pending"), CONFIRMED("confirmed") }
internal enum class FontTaskTerminal(val value: String) { SUCCESS("success"), FAILED("failed"), CANCELLED("cancelled") }

/** Opaque App identity; backend IDs stay inside the registry and are never exported. */
internal class FontTaskRequest internal constructor(val id: String)

internal data class FontTaskTimingSnapshot(
    val requestId: String,
    val operation: FontTaskOperation,
    val origin: FontTaskOrigin,
    val backendBound: Boolean,
    val terminal: FontTaskTerminal?,
    val observer: FontTaskObserver,
    val cleanup: FontTaskCleanup,
    val requestClosedMs: Long?,
    val requestToObservedTerminalMs: Long?,
)

/** Process-only evidence. It does not change task ownership, polling, or operation state. */
internal class FontTaskTimingRegistry(private val nowMs: () -> Long, capacity: Int = 8) {
    private val capacity = capacity.coerceIn(0, 8)
    private class Entry(
        val request: FontTaskRequest,
        val operation: FontTaskOperation,
        val origin: FontTaskOrigin,
        val acceptedAt: Long?,
        var taskId: String = "",
        var terminal: FontTaskTerminal? = null,
        var observer: FontTaskObserver = FontTaskObserver.WAITING,
        var cleanup: FontTaskCleanup = FontTaskCleanup.NONE,
        var closedMs: Long? = null,
        var terminalMs: Long? = null,
    )

    private val entries = mutableListOf<Entry>()

    @Synchronized
    fun begin(operation: FontTaskOperation): FontTaskRequest =
        add(operation, FontTaskOrigin.APP_REQUEST, clock())

    @Synchronized
    fun bind(request: FontTaskRequest?, operation: FontTaskOperation, taskId: String) {
        val entry = find(request) ?: return
        if (entry.operation != operation || taskId.isBlank() || entry.taskId.isNotEmpty()) return
        if (entries.any { it !== entry && it.operation == operation && it.taskId == taskId }) return
        entry.taskId = taskId
    }

    /** Same-process recreation retains the exact request; an unknown task has no click clock. */
    @Synchronized
    fun attach(operation: FontTaskOperation, taskId: String): FontTaskRequest? {
        if (taskId.isBlank()) return null
        entries.firstOrNull { it.operation == operation && it.taskId == taskId }?.let { return it.request }
        val request = add(operation, FontTaskOrigin.RECOVERED, null)
        find(request)?.taskId = taskId
        return request
    }

    @Synchronized
    fun observe(request: FontTaskRequest?, operation: FontTaskOperation, taskId: String, state: String) {
        val entry = find(request) ?: return
        if (entry.operation != operation || entry.taskId.isBlank() || entry.taskId != taskId || entry.terminal != null) return
        val terminal = FontTaskTerminal.entries.firstOrNull { it.value == state } ?: return
        val elapsed = elapsed(entry)
        entry.terminal = terminal
        if (entry.observer == FontTaskObserver.WAITING) {
            entry.observer = FontTaskObserver.TERMINAL
            entry.closedMs = elapsed
            if (entry.cleanup != FontTaskCleanup.PENDING) entry.terminalMs = elapsed
        }
    }

    @Synchronized
    fun stopped(request: FontTaskRequest?, cancelled: Boolean, cleanupPending: Boolean = false) {
        val entry = find(request) ?: return
        if (cleanupPending) {
            entry.cleanup = FontTaskCleanup.PENDING
            entry.terminalMs = null
        }
        if (entry.observer != FontTaskObserver.WAITING) return
        entry.observer = if (cancelled) FontTaskObserver.CANCELLED else FontTaskObserver.FAILED
        entry.closedMs = elapsed(entry)
        // Stopping a status observer or acknowledging cleanup is not a task terminal response.
    }

    @Synchronized
    fun cleanup(operation: FontTaskOperation, taskId: String, confirmed: Boolean) {
        val entry = entries.firstOrNull { it.operation == operation && it.taskId == taskId } ?: return
        entry.cleanup = if (confirmed) FontTaskCleanup.CONFIRMED else FontTaskCleanup.PENDING
        if (!confirmed) entry.terminalMs = null
        // A later cleanup receipt cannot restore a previously unconfirmed click total.
    }

    @Synchronized
    fun snapshot(): List<FontTaskTimingSnapshot> = entries.map {
        FontTaskTimingSnapshot(it.request.id, it.operation, it.origin, it.taskId.isNotBlank(),
            it.terminal, it.observer, it.cleanup, it.closedMs, it.terminalMs)
    }

    private fun add(operation: FontTaskOperation, origin: FontTaskOrigin, acceptedAt: Long?): FontTaskRequest {
        val request = FontTaskRequest(UUID.randomUUID().toString())
        if (capacity <= 0) return request
        if (entries.size >= capacity) {
            // Prefer completed evidence; an all-active registry still stays strictly bounded.
            val index = entries.indexOfFirst { it.observer != FontTaskObserver.WAITING && it.cleanup != FontTaskCleanup.PENDING }
            entries.removeAt(if (index >= 0) index else 0)
        }
        entries += Entry(request, operation, origin, acceptedAt)
        return request
    }

    private fun find(request: FontTaskRequest?): Entry? = entries.firstOrNull { it.request === request }
    private fun clock(): Long? = runCatching { nowMs().takeIf { it >= 0L } }.getOrNull()
    private fun elapsed(entry: Entry): Long? {
        val start = entry.acceptedAt ?: return null
        val end = clock() ?: return null
        return if (end >= start) end - start else null
    }
}

/** Fixed keys, enums, opaque random IDs, and durations only: no backend task ID or font metadata. */
internal fun sanitizedFontTaskTiming(records: List<FontTaskTimingSnapshot>): String = buildString {
    val safeRecords = records.take(8).filter {
        it.requestId.matches(Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"))
    }
    appendLine("schema=luoshu-app-font-task-timing-v1")
    appendLine("scope=accepted-app-request-to-observed-task-terminal")
    appendLine("clock=elapsedRealtime")
    appendLine("records=${safeRecords.size}")
    safeRecords.forEachIndexed { index, record ->
        val prefix = "request.${index + 1}."
        appendLine("${prefix}id=${record.requestId}")
        appendLine("${prefix}operation=${record.operation.value}")
        appendLine("${prefix}origin=${record.origin.value}")
        appendLine("${prefix}backendBound=${record.backendBound}")
        appendLine("${prefix}terminal=${record.terminal?.value ?: "unknown"}")
        appendLine("${prefix}observer=${record.observer.value}")
        appendLine("${prefix}cleanup=${record.cleanup.value}")
        appendLine("${prefix}requestClosedMs=${record.requestClosedMs?.takeIf { it >= 0L } ?: "unknown"}")
        val total = record.requestToObservedTerminalMs?.takeIf {
            it >= 0L && record.origin == FontTaskOrigin.APP_REQUEST && record.terminal != null &&
                record.observer == FontTaskObserver.TERMINAL && record.cleanup != FontTaskCleanup.PENDING
        }
        appendLine("${prefix}requestToObservedTerminalMs=${total ?: "unknown"}")
    }
}

internal object AppFontTaskTimings {
    val registry = FontTaskTimingRegistry(nowMs = { SystemClock.elapsedRealtime() })
    fun sanitizedSnapshot(): String = runCatching { sanitizedFontTaskTiming(registry.snapshot()) }
        .getOrDefault("schema=luoshu-app-font-task-timing-v1\navailability=unavailable\n")
}
