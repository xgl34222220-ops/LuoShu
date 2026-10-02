package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class FontCacheStartupTest {
    @Test
    fun immediateRestoreCannotReadItsJobBeforeTheFieldIsAssigned() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            var publishedJob: Job? = null
            var readCount = 0
            val created = scope.createFontCacheRestore {
                assertNotNull("Restore ran before its owning Job was published", publishedJob)
                readCount++ // Empty/in-memory caches do not have to suspend.
            }
            assertEquals(0, readCount)
            publishedJob = created
            created.start()
            created.join()
            assertEquals(1, readCount)
            assertTrue(created.isCompleted)
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun refreshAfterImmediateEmptyCacheJoinsAnInitializedJob() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val events = mutableListOf<String>()
            val cacheLoadJob = scope.createFontCacheRestore { events += "empty-cache-ready" }
            cacheLoadJob.start()
            val request = scope.launch(start = CoroutineStart.UNDISPATCHED) {
                cacheLoadJob.join()
                events += "refresh"
            }
            request.join()
            assertEquals(listOf("empty-cache-ready", "refresh"), events)
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun refreshWaitsForSlowCacheWithoutReentrantSelfJoin() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val cacheRead = CompletableDeferred<Unit>()
            val events = mutableListOf<String>()
            val cacheLoadJob = scope.createFontCacheRestore { cacheRead.await(); events += "cached-rows" }
            cacheLoadJob.start()
            val request = scope.launch(start = CoroutineStart.UNDISPATCHED) {
                cacheLoadJob.join()
                events += "refresh"
            }
            assertTrue(request.isActive)
            assertTrue(events.isEmpty())
            cacheRead.complete(Unit)
            request.join()
            assertEquals(listOf("cached-rows", "refresh"), events)
        } finally {
            scope.cancel()
        }
    }

    @Test
    fun cancelledOwnerNeverStartsCacheWork() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        var ran = false
        val cacheLoadJob = scope.createFontCacheRestore { ran = true }
        scope.cancel()
        cacheLoadJob.start()
        cacheLoadJob.join()
        assertFalse(ran)
        assertTrue(cacheLoadJob.isCancelled)
    }
}
