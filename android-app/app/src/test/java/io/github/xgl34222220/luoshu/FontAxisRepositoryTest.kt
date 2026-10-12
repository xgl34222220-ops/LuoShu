package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FontAxisRepositoryTest {
    @Test
    fun existingObserverReceivesSuccessfulRetryWithoutPublishingFailure() = runBlocking {
        val repository = FontAxisRepository()
        val observed = async(start = CoroutineStart.UNDISPATCHED) {
            repository.successes.first { "source" in it }.getValue("source")
        }
        repository.resolve("source") { WeightAxisInfo(loading = false, error = "命令执行超时") }
        assertTrue(repository.successes.value.isEmpty())
        assertTrue(!observed.isCompleted)
        val ready = repository.resolve("source") { info(600f) }
        assertEquals(ready, observed.await())
        assertEquals(ready, repository.successes.value["source"])
    }

    @Test
    fun publishedSnapshotsRemainImmutableAndFollowActualLruBound() = runBlocking {
        val repository = FontAxisRepository(maxEntries = 2)
        repository.resolve("a") { info(450f) }
        repository.resolve("b") { info(500f) }
        val prior = repository.successes.value
        repository.cached("a")
        repository.resolve("c") { info(600f) }
        assertEquals(setOf("a", "b"), prior.keys)
        assertEquals(setOf("a", "c"), repository.successes.value.keys)
        assertNull(repository.cached("b"))
        assertEquals(600f, repository.successes.value.getValue("c").axes.single().default)
    }

    private fun info(default: Float = 450f) = WeightAxisInfo(
        loading = false, hasWeight = true,
        axes = listOf(VariableAxisInfo("wght", 100f, default, 900f)),
    )

    @Test
    fun simultaneousPickerAndControlsShareOneRead() = runBlocking {
        val repository = FontAxisRepository()
        val started = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        var reads = 0
        val first = async { repository.resolve("same-source") {
            reads++; started.complete(Unit); release.await(); info()
        } }
        started.await()
        val second = async { repository.resolve("same-source") { reads++; info(700f) } }
        release.complete(Unit)
        assertEquals(first.await(), second.await())
        assertEquals(1, reads)
    }

    @Test
    fun sameNameReplacementHasItsOwnDefaults() = runBlocking {
        val repository = FontAxisRepository()
        repository.resolve("same-name|same-size|same-date|old-content") { info(450f) }
        val fresh = repository.resolve("same-name|same-size|same-date|new-content") { info(600f) }
        assertEquals(600f, fresh.axes.single().default)
        assertEquals(450f, repository.cached("same-name|same-size|same-date|old-content")!!.axes.single().default)
    }

    @Test
    fun timeoutOrMalformedResultCannotPoisonDefaultCache() = runBlocking {
        val repository = FontAxisRepository()
        val failed = repository.resolve("source") { WeightAxisInfo(loading = false, error = "命令执行超时") }
        assertTrue(failed.error.isNotBlank())
        assertNull(repository.cached("source"))
        assertEquals(info(), repository.resolve("source") { info() })
    }

    @Test
    fun cancellationReleasesReaderAndDoesNotCacheFallback() = runBlocking {
        val repository = FontAxisRepository()
        val started = CompletableDeferred<Unit>()
        val cancelled = launch { repository.resolve("source") {
            started.complete(Unit); CompletableDeferred<Unit>().await(); info()
        } }
        started.await(); cancelled.cancelAndJoin()
        assertNull(repository.cached("source"))
        assertEquals(info(), repository.resolve("source") { info() })
    }

    @Test
    fun cacheRetainsRecentRevisionsWithinItsBound() = runBlocking {
        val repository = FontAxisRepository(maxEntries = 2)
        repository.resolve("a") { info() }; repository.resolve("b") { info() }
        repository.cached("a")
        repository.resolve("c") { info() }
        assertNull(repository.cached("b"))
        assertEquals(info(), repository.cached("a"))
        assertEquals(info(), repository.cached("c"))
    }

    @Test
    fun widthOnlyFontKeepsDeclaredDefaultsWithoutInventingWeightAxis() = runBlocking {
        val repository = FontAxisRepository()
        val declared = WeightAxisInfo(loading = false, axes = listOf(
            VariableAxisInfo("wdth", 75f, 100f, 125f),
            VariableAxisInfo("HIDN", 0f, 1f, 2f, hidden = true),
        ))
        repository.resolve("width-only") { declared }
        assertEquals(listOf("wdth", "HIDN"), repository.cached("width-only")!!.axes.map { it.tag })
        assertEquals(listOf("wdth"), declared.visibleAxes.map { it.tag })
    }
}
