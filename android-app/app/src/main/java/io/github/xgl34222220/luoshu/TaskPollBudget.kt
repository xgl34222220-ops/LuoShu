package io.github.xgl34222220.luoshu

/** Counts status-query time as well as delays; background UI observation is suspended. */
internal class TaskPollBudget(
    timeoutMs: Long,
    private val nowMs: () -> Long = { System.nanoTime() / 1_000_000L },
) {
    private val startedAt = nowMs()
    private var pausedMs = 0L
    private var deadlineMs = timeoutMs

    val elapsedMs: Long get() = (nowMs() - startedAt - pausedMs).coerceAtLeast(0L)
    val remainingMs: Long get() = (deadlineMs - elapsedMs).coerceAtLeast(0L)

    fun excludePause(durationMs: Long) {
        pausedMs += durationMs.coerceAtLeast(0L)
    }

    fun extendTo(timeoutMs: Long) {
        deadlineMs = maxOf(deadlineMs, timeoutMs)
    }
}
