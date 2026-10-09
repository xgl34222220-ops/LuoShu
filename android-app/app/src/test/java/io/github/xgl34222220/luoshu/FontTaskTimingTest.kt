package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class FontTaskTimingTest {
    private var now = 10_000L
    private fun registry(capacity: Int = 8) = FontTaskTimingRegistry({ now }, capacity)
    private fun receipt(task: String) = ShellResult(0, "{\"status\":\"ok\",\"data\":{\"task\":\"$task\",\"cleaned\":true}}", "")

    @Test
    fun includesSubmissionValidationAndBackgroundTimeWithoutAPollingClockReset() {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.SWITCH)
        now = 41_000L // Submission follows prewarm and validation.
        registry.bind(request, FontTaskOperation.SWITCH, "owned")
        now = 941_000L // Background/suspend time remains part of elapsedRealtime.
        registry.observe(request, FontTaskOperation.SWITCH, "owned", "success")
        assertEquals(931_000L, registry.snapshot().single().requestToObservedTerminalMs)
    }

    @Test
    fun requiresTheCapturedRequestOperationAndExactBackendIdentity() {
        val registry = registry()
        val switch = registry.begin(FontTaskOperation.SWITCH)
        val mix = registry.begin(FontTaskOperation.MIX)
        registry.bind(switch, FontTaskOperation.MIX, "wrong")
        registry.bind(switch, FontTaskOperation.SWITCH, "owned-switch")
        registry.bind(mix, FontTaskOperation.MIX, "owned-mix")
        now += 50L
        registry.observe(switch, FontTaskOperation.MIX, "owned-switch", "success")
        registry.observe(switch, FontTaskOperation.SWITCH, "owned-mix", "success")
        registry.observe(switch, FontTaskOperation.SWITCH, "", "success")
        registry.observe(switch, FontTaskOperation.SWITCH, "owned-switch", "cleanup-pending")
        assertTrue(registry.snapshot().all { it.terminal == null })
        registry.observe(mix, FontTaskOperation.MIX, "owned-mix", "success")
        assertNull(registry.snapshot().first().requestToObservedTerminalMs)
        assertEquals(50L, registry.snapshot().last().requestToObservedTerminalMs)
    }

    @Test
    fun capturesTheFirstTerminalOnlyAndDoesNotCloseANewerRequest() {
        val registry = registry()
        val old = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(old, FontTaskOperation.SWITCH, "old")
        now += 15L
        registry.observe(old, FontTaskOperation.SWITCH, "old", "failed")
        val next = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(next, FontTaskOperation.SWITCH, "new")
        now += 500L
        registry.observe(old, FontTaskOperation.SWITCH, "old", "success")
        registry.stopped(old, cancelled = true)
        assertEquals(FontTaskTerminal.FAILED, registry.snapshot().first().terminal)
        assertEquals(15L, registry.snapshot().first().requestToObservedTerminalMs)
        assertEquals(FontTaskObserver.WAITING, registry.snapshot().last().observer)
    }

    @Test
    fun cannotRebindOrOverwriteAnExistingBackendIdentity() {
        val registry = registry()
        val first = registry.begin(FontTaskOperation.SWITCH)
        val second = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(first, FontTaskOperation.SWITCH, "shared")
        registry.bind(second, FontTaskOperation.SWITCH, "shared")
        registry.bind(first, FontTaskOperation.SWITCH, "replacement")
        assertSame(first, registry.attach(FontTaskOperation.SWITCH, "shared"))
        registry.observe(first, FontTaskOperation.SWITCH, "replacement", "success")
        assertNull(registry.snapshot().first().terminal)
        now += 20L
        registry.observe(first, FontTaskOperation.SWITCH, "shared", "success")
        assertEquals(20L, registry.snapshot().first().requestToObservedTerminalMs)
        assertFalse(registry.snapshot().last().backendBound)
        assertNull(registry.snapshot().last().requestToObservedTerminalMs)
    }

    @Test
    fun recreationAttachesToTheSameProcessRequestWithoutRestartingItsClock() {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.MIX)
        registry.bind(request, FontTaskOperation.MIX, "mix-task")
        now += 700L
        val attached = registry.attach(FontTaskOperation.MIX, "mix-task")
        assertSame(request, attached)
        registry.observe(attached, FontTaskOperation.MIX, "mix-task", "cancelled")
        assertEquals(700L, registry.snapshot().single().requestToObservedTerminalMs)
        assertEquals(FontTaskTerminal.CANCELLED, registry.snapshot().single().terminal)
    }

    @Test
    fun aRecoveredTaskHasNoInventedClickClockEvenWhenATerminalIsObserved() {
        val registry = registry()
        val recovered = registry.attach(FontTaskOperation.SWITCH, "from-another-process")
        now += 9_000L
        registry.observe(recovered, FontTaskOperation.SWITCH, "from-another-process", "success")
        val record = registry.snapshot().single()
        assertEquals(FontTaskOrigin.RECOVERED, record.origin)
        assertEquals(FontTaskTerminal.SUCCESS, record.terminal)
        assertNull(record.requestClosedMs)
        assertNull(record.requestToObservedTerminalMs)
    }

    @Test
    fun submissionOrObserverFailureCannotBecomeAClickTotalAfterReattachment() {
        val registry = registry()
        val rejected = registry.begin(FontTaskOperation.SWITCH)
        now += 33L
        registry.stopped(rejected, cancelled = false)
        val submitted = registry.begin(FontTaskOperation.MIX)
        registry.bind(submitted, FontTaskOperation.MIX, "task")
        now += 44L
        registry.stopped(submitted, cancelled = false)
        now += 99L
        registry.observe(registry.attach(FontTaskOperation.MIX, "task"), FontTaskOperation.MIX, "task", "success")
        assertEquals(33L, registry.snapshot().first().requestClosedMs)
        assertNull(registry.snapshot().first().terminal)
        assertEquals(FontTaskObserver.FAILED, registry.snapshot().last().observer)
        assertEquals(44L, registry.snapshot().last().requestClosedMs)
        assertTrue(registry.snapshot().all { it.requestToObservedTerminalMs == null })
    }

    @Test
    fun cleanupPendingInvalidatesATotalAndLaterCleanupCannotRestoreIt() {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.MIX)
        registry.bind(request, FontTaskOperation.MIX, "task")
        now += 55L
        registry.observe(request, FontTaskOperation.MIX, "task", "failed")
        registry.cleanup(FontTaskOperation.SWITCH, "task", confirmed = false)
        assertEquals(55L, registry.snapshot().single().requestToObservedTerminalMs)
        registry.cleanup(FontTaskOperation.MIX, "task", confirmed = false)
        assertNull(registry.snapshot().single().requestToObservedTerminalMs)
        registry.cleanup(FontTaskOperation.MIX, "task", confirmed = true)
        assertEquals(FontTaskCleanup.CONFIRMED, registry.snapshot().single().cleanup)
        assertNull(registry.snapshot().single().requestToObservedTerminalMs)
    }

    @Test
    fun unconfirmedCleanupAfterAReceiptStaysConservativeAndCannotTouchANewerRequest() {
        val registry = registry()
        val old = registry.begin(FontTaskOperation.MIX)
        registry.bind(old, FontTaskOperation.MIX, "old")
        now += 60L
        registry.observe(old, FontTaskOperation.MIX, "old", "failed")
        registry.cleanup(FontTaskOperation.MIX, "old", confirmed = true)
        val next = registry.begin(FontTaskOperation.MIX)
        registry.bind(next, FontTaskOperation.MIX, "next")
        repeat(3) {
            registry.cleanup(FontTaskOperation.MIX, "old", confirmed = true)
            registry.cleanup(FontTaskOperation.MIX, "old", confirmed = false)
            registry.stopped(old, cancelled = true, cleanupPending = true)
        }
        assertEquals(FontTaskCleanup.PENDING, registry.snapshot().first().cleanup)
        assertNull(registry.snapshot().first().requestToObservedTerminalMs)
        registry.cleanup(FontTaskOperation.MIX, "old", confirmed = true)
        registry.cleanup(FontTaskOperation.MIX, "old", confirmed = true)
        assertEquals(FontTaskCleanup.CONFIRMED, registry.snapshot().first().cleanup)
        assertNull(registry.snapshot().first().requestToObservedTerminalMs)
        val fresh = registry.snapshot().last()
        assertEquals(FontTaskCleanup.NONE, fresh.cleanup)
        assertEquals(FontTaskObserver.WAITING, fresh.observer)
        assertNull(fresh.terminal)
        assertNull(fresh.requestToObservedTerminalMs)
    }

    @Test
    fun prefersCompletedEvictionAndIgnoresAnEvictedRequestsLateCallbacks() {
        val registry = registry(capacity = 2)
        val active = registry.begin(FontTaskOperation.MIX)
        registry.bind(active, FontTaskOperation.MIX, "active")
        val finished = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(finished, FontTaskOperation.SWITCH, "finished")
        registry.observe(finished, FontTaskOperation.SWITCH, "finished", "success")
        val newest = registry.begin(FontTaskOperation.SWITCH)
        registry.observe(finished, FontTaskOperation.SWITCH, "finished", "failed")
        assertEquals(listOf(active.id, newest.id), registry.snapshot().map { it.requestId })
        repeat(30) { registry.begin(FontTaskOperation.SWITCH) }
        registry.stopped(active, cancelled = true)
        assertEquals(2, registry.snapshot().size)
        assertTrue(registry.snapshot().all { it.observer == FontTaskObserver.WAITING })
        val hardBounded = registry(capacity = Int.MAX_VALUE)
        repeat(30) { hardBounded.begin(FontTaskOperation.MIX) }
        assertEquals(8, hardBounded.snapshot().size)
    }

    @Test
    fun unavailableOrReversedClockDoesNotFabricateZero() {
        val unavailable = FontTaskTimingRegistry({ error("clock unavailable") })
        val unknown = unavailable.begin(FontTaskOperation.SWITCH)
        unavailable.bind(unknown, FontTaskOperation.SWITCH, "task")
        unavailable.observe(unknown, FontTaskOperation.SWITCH, "task", "success")
        assertNull(unavailable.snapshot().single().requestToObservedTerminalMs)
        val registry = registry()
        val reversed = registry.begin(FontTaskOperation.MIX)
        registry.bind(reversed, FontTaskOperation.MIX, "task")
        now = 9_999L
        registry.observe(reversed, FontTaskOperation.MIX, "task", "success")
        assertNull(registry.snapshot().single().requestToObservedTerminalMs)
    }

    @Test
    fun diagnosticIsBoundedAndOmitsBackendIdentityAndUntrustedSnapshotValues() {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(request, FontTaskOperation.SWITCH, "/private/font-name-timestamp-pid; $(secret)")
        val record = registry.snapshot().single()
        val output = sanitizedFontTaskTiming(listOf(record))
        assertFalse(output.contains("private"))
        assertFalse(output.contains("font-name"))
        assertFalse(output.contains("timestamp"))
        assertFalse(output.contains("secret"))
        assertTrue(output.contains("requestToObservedTerminalMs=unknown"))
        assertEquals("records=0", sanitizedFontTaskTiming(listOf(record.copy(requestId = "injected\nfont=secret"))).lineSequence().first { it.startsWith("records=") })
        val invalid = sanitizedFontTaskTiming(listOf(record.copy(requestClosedMs = -1L, requestToObservedTerminalMs = 123L)))
        assertTrue(invalid.contains("requestClosedMs=unknown"))
        assertTrue(invalid.contains("requestToObservedTerminalMs=unknown"))
        assertTrue(sanitizedFontTaskTiming(List(50) { record }).contains("records=8\n"))
    }

    @Test
    fun actualOwnedTaskSuccessRecordsATerminalWithoutAnExtraCleanupRequest() = runBlocking {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(request, FontTaskOperation.SWITCH, "owned")
        val result = awaitOwnedFontTask("owned", "cancel owned", { _, _ -> error("Unexpected cleanup") },
            executor = { _, _ -> error("Unexpected Root request") }) {
            now += 70L
            registry.observe(request, FontTaskOperation.SWITCH, "owned", "success")
            "success"
        }
        assertEquals("success", result)
        assertEquals(70L, registry.snapshot().single().requestToObservedTerminalMs)
    }

    @Test
    fun actualOwnedTaskDuplicatePairUsesItsCapturedUnboundHandleAndNeverAnOlderClock() = runBlocking {
        val registry = registry()
        val older = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(older, FontTaskOperation.SWITCH, "duplicate")
        now += 500L
        val current = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(current, FontTaskOperation.SWITCH, "duplicate")
        assertFalse(registry.snapshot().last().backendBound)
        assertSame(older, registry.attach(FontTaskOperation.SWITCH, "duplicate"))
        val result = awaitOwnedFontTask("duplicate", "cancel duplicate", { _, _ -> error("Unexpected cleanup") },
            executor = { _, _ -> error("Unexpected Root request") }) {
            now += 70L
            // Normal start passes the captured request; it must not attach by the repeated pair.
            registry.observe(current, FontTaskOperation.SWITCH, "duplicate", "success")
            "success"
        }
        registry.stopped(current, cancelled = false)
        assertEquals("success", result)
        assertEquals(FontTaskObserver.WAITING, registry.snapshot().first().observer)
        assertNull(registry.snapshot().first().terminal)
        assertNull(registry.snapshot().first().requestClosedMs)
        assertNull(registry.snapshot().first().requestToObservedTerminalMs)
        assertEquals(FontTaskObserver.FAILED, registry.snapshot().last().observer)
        assertNull(registry.snapshot().last().terminal)
        assertNull(registry.snapshot().last().requestToObservedTerminalMs)
    }

    @Test
    fun actualOwnedTaskCancellationWaitsForCleanupButDoesNotInventATerminal() = runBlocking {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.MIX)
        registry.bind(request, FontTaskOperation.MIX, "owned")
        val observing = CompletableDeferred<Unit>()
        val cleaning = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val job = launch {
            try {
                awaitOwnedFontTask("owned", "cancel owned", { cleaned, _ -> registry.cleanup(FontTaskOperation.MIX, "owned", cleaned) },
                    executor = { command, _ ->
                        assertEquals("cancel owned", command)
                        cleaning.complete(Unit)
                        release.await()
                        receipt("owned")
                    }) {
                    observing.complete(Unit)
                    delay(30_000L)
                }
            } catch (cancelled: CancellationException) {
                registry.stopped(request, cancelled = true, cleanupPending = cancelled.cleanupUnconfirmed())
                throw cancelled
            }
        }
        withTimeout(3_000L) {
            observing.await()
            job.cancel()
            cleaning.await()
            assertFalse(job.isCompleted)
            assertEquals(FontTaskObserver.WAITING, registry.snapshot().single().observer)
            now += 200L
            release.complete(Unit)
            job.join()
        }
        val record = registry.snapshot().single()
        assertEquals(FontTaskCleanup.CONFIRMED, record.cleanup)
        assertEquals(FontTaskObserver.CANCELLED, record.observer)
        assertEquals(200L, record.requestClosedMs)
        assertNull(record.terminal)
        assertNull(record.requestToObservedTerminalMs)
    }

    @Test
    fun actualOwnedTaskFailureRejectsAnotherTasksCleanupReceipt() = runBlocking {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.SWITCH)
        registry.bind(request, FontTaskOperation.SWITCH, "owned")
        val failure = IllegalStateException("private observer error")
        try {
            awaitOwnedFontTask("owned", "cancel owned", { cleaned, _ -> registry.cleanup(FontTaskOperation.SWITCH, "owned", cleaned) },
                executor = { _, _ -> receipt("other") }) { throw failure }
        } catch (error: Throwable) {
            assertSame(failure, error)
            assertTrue(error.cleanupUnconfirmed())
            registry.stopped(request, cancelled = false, cleanupPending = error.cleanupUnconfirmed())
        }
        val record = registry.snapshot().single()
        assertEquals(FontTaskCleanup.PENDING, record.cleanup)
        assertEquals(FontTaskObserver.FAILED, record.observer)
        assertNull(record.terminal)
        assertNull(record.requestToObservedTerminalMs)
        assertFalse(sanitizedFontTaskTiming(registry.snapshot()).contains(failure.message!!))
    }

    @Test
    fun actualOwnedTaskFailedTerminalKeepsTheObservedTimeWhenCleanupIsVerified() = runBlocking {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.MIX)
        registry.bind(request, FontTaskOperation.MIX, "owned")
        try {
            awaitOwnedFontTask("owned", "cancel owned", { cleaned, _ -> registry.cleanup(FontTaskOperation.MIX, "owned", cleaned) },
                executor = { _, _ -> now += 500L; receipt("owned") }) {
                now += 90L
                registry.observe(request, FontTaskOperation.MIX, "owned", "failed")
                error("terminal failed") // The ViewModel's existing non-success .also throws.
            }
        } catch (error: IllegalStateException) {
            registry.stopped(request, cancelled = false, cleanupPending = error.cleanupUnconfirmed())
        }
        assertEquals(FontTaskTerminal.FAILED, registry.snapshot().single().terminal)
        assertEquals(FontTaskCleanup.CONFIRMED, registry.snapshot().single().cleanup)
        assertEquals(90L, registry.snapshot().single().requestToObservedTerminalMs)
    }

    @Test
    fun actualOwnedTaskUnconfirmedCleanupWithholdsEvenAnObservedFailedTotal() = runBlocking {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.MIX)
        registry.bind(request, FontTaskOperation.MIX, "owned")
        try {
            awaitOwnedFontTask("owned", "cancel owned", { cleaned, _ -> registry.cleanup(FontTaskOperation.MIX, "owned", cleaned) },
                executor = { _, _ -> receipt("other") }) {
                now += 90L
                registry.observe(request, FontTaskOperation.MIX, "owned", "failed")
                error("terminal failed")
            }
        } catch (error: IllegalStateException) {
            assertTrue(error.cleanupUnconfirmed())
            registry.stopped(request, cancelled = false, cleanupPending = error.cleanupUnconfirmed())
        }
        assertEquals(FontTaskTerminal.FAILED, registry.snapshot().single().terminal)
        assertEquals(FontTaskCleanup.PENDING, registry.snapshot().single().cleanup)
        assertNull(registry.snapshot().single().requestToObservedTerminalMs)
    }

    @Test
    fun cancellationBeforeLaunchStartsClosesOnlyItsAcceptedRequest() = runBlocking {
        val registry = registry()
        val request = registry.begin(FontTaskOperation.SWITCH)
        val job = launch(start = CoroutineStart.LAZY) { error("Launch should not start") }
        job.invokeOnCompletion { cause -> registry.stopped(request, cancelled = cause is CancellationException) }
        now += 12L
        job.cancel()
        job.join()
        assertEquals(FontTaskObserver.CANCELLED, registry.snapshot().single().observer)
        assertEquals(12L, registry.snapshot().single().requestClosedMs)
        assertNull(registry.snapshot().single().terminal)
        assertNull(registry.snapshot().single().requestToObservedTerminalMs)
    }
}
