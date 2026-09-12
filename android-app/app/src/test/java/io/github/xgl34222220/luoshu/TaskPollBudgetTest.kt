package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Test

class TaskPollBudgetTest {
    @Test
    fun slowRootRequestsConsumeTheSameDeadlineAsPollingDelays() {
        var now = 1_000L
        val budget = TaskPollBudget(390_000L) { now }
        repeat(24) { now += 1_000L + 15_000L }
        assertEquals(6_000L, budget.remainingMs)
        now += 15_000L
        assertEquals(0L, budget.remainingMs)
    }

    @Test
    fun backgroundPauseDoesNotTurnACompletedTaskIntoAUiTimeout() {
        var now = 0L
        val budget = TaskPollBudget(390_000L) { now }
        now = 10_000L
        now += 3_600_000L
        budget.excludePause(3_600_000L)
        assertEquals(380_000L, budget.remainingMs)
        now += 5_000L
        assertEquals(375_000L, budget.remainingMs)
    }

    @Test
    fun anAdvertisedDeadlineDoesNotRestartOnEachStatusReply() {
        var now = 0L
        val budget = TaskPollBudget(390_000L) { now }
        now = 300_000L
        budget.extendTo(750_000L)
        assertEquals(450_000L, budget.remainingMs)
        now = 740_000L
        budget.extendTo(750_000L)
        assertEquals(10_000L, budget.remainingMs)
    }
}
