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

/**
 * Status-poll cadence for a running font task: 1 s for the first 30 s, then 2 s; once the reported
 * state/progress/message has stayed identical for several polls, back off to at most 4 s. Any change
 * resets [unchangedPolls] to 0 and restores the normal cadence.
 */
internal fun taskPollIntervalMs(elapsedMs: Long, unchangedPolls: Int): Long {
    val base = if (elapsedMs < 30_000L) 1_000L else 2_000L
    return when {
        unchangedPolls >= 6 -> 4_000L
        unchangedPolls >= 3 -> maxOf(base, 2_000L)
        else -> base
    }
}
