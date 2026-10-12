package io.github.xgl34222220.luoshu.ui.home

import androidx.lifecycle.Lifecycle
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceTrustPollingTest {
    @Test
    fun visibleHostDoesNotWait() = runBlocking {
        withTimeout(500L) { awaitLifecycleStarted(MutableStateFlow(Lifecycle.State.RESUMED)) }
        withTimeout(500L) { awaitLifecycleStarted(MutableStateFlow(Lifecycle.State.STARTED)) }
    }

    @Test
    fun backgroundHostSuspendsTheNextRootReadUntilItIsVisibleAgain() = runBlocking {
        val state = MutableStateFlow(Lifecycle.State.CREATED)
        var reads = 0
        val poll = async {
            awaitLifecycleStarted(state)
            reads += 1
        }
        delay(150L)
        assertFalse(poll.isCompleted)
        assertTrue(reads == 0)
        state.value = Lifecycle.State.STARTED
        withTimeout(1_000L) { poll.await() }
        assertTrue(reads == 1)
    }
}
