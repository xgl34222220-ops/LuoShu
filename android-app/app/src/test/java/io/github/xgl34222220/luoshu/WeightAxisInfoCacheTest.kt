package io.github.xgl34222220.luoshu

import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WeightAxisInfoCacheTest {
    private val font = FontItem(
        id = "DonorVF", name = "DonorVF", format = "TTF", size = "12 MB", date = "2026-09-12",
        variable = true, valid = true, error = "", weights = listOf("variable"),
        sourceRevision = "v3:original-fingerprint:1:20000100",
    )
    private val loaded = WeightAxisInfo(
        loading = false, hasWeight = true, min = 150, default = 330, max = 700,
        axes = listOf(VariableAxisInfo("wght", 150f, 330f, 700f)),
    )

    @Test
    fun failedReadIsNotCachedAndRetryCanRecover() = runBlocking {
        val cache = WeightAxisInfoCache()
        var attempts = 0
        val loader: suspend (FontItem) -> WeightAxisInfo = {
            attempts += 1
            if (attempts == 1) WeightAxisInfo(loading = false, error = "命令执行超时") else loaded
        }
        assertTrue(cache.load(font, loader).error.isNotBlank())
        assertNull(cache.get(font))
        assertEquals(loaded, cache.load(font, loader))
        assertEquals(loaded, cache.get(font))
        assertEquals(2, attempts)
    }

    @Test
    fun successfulReadIsReusedForUnchangedSource() = runBlocking {
        val cache = WeightAxisInfoCache()
        var attempts = 0
        repeat(2) {
            assertEquals(loaded, cache.load(font) { attempts += 1; loaded })
        }
        assertEquals(1, attempts)
    }

    @Test
    fun sameFamilyWithChangedFileMetadataReloadsAxes() = runBlocking {
        for (changed in listOf(
            font.copy(size = "14 MB"), font.copy(date = "2026-09-13"),
            font.copy(format = "TTC"), font.copy(variable = false),
            font.copy(weights = listOf("regular", "bold")),
        )) {
            val cache = WeightAxisInfoCache()
            var attempts = 0
            cache.load(font) { attempts += 1; loaded }
            assertNull(cache.get(changed))
            val revised = loaded.copy(max = 900)
            assertEquals(revised, cache.load(changed) { attempts += 1; revised })
            assertEquals(2, attempts)
            assertNull(cache.get(font))
        }
    }

    @Test
    fun concurrentRequestsShareSuccessfulRead() = runBlocking {
        val cache = WeightAxisInfoCache()
        var attempts = 0
        val loader: suspend (FontItem) -> WeightAxisInfo = {
            attempts += 1
            delay(20)
            loaded
        }
        val first = async { cache.load(font, loader) }
        val second = async { cache.load(font, loader) }
        assertEquals(loaded, first.await())
        assertEquals(loaded, second.await())
        assertEquals(1, attempts)
    }

    @Test
    fun sameDisplaySizeAndDateWithNewFingerprintReloadsAxes() = runBlocking {
        val cache = WeightAxisInfoCache()
        val replaced = font.copy(sourceRevision = "v3:changed-fingerprint:1:20000500")
        assertEquals(font.size, replaced.size)
        assertEquals(font.date, replaced.date)
        cache.load(font) { loaded }
        assertNull(cache.get(replaced))
        val changedAxes = loaded.copy(default = 400)
        assertEquals(changedAxes, cache.load(replaced) { changedAxes })
    }

    @Test
    fun legacySourceWithoutFingerprintIsNotPersistentlyCached() = runBlocking {
        val cache = WeightAxisInfoCache()
        val legacy = font.copy(sourceRevision = "")
        var attempts = 0
        repeat(2) { cache.load(legacy) { attempts += 1; loaded } }
        assertNull(cache.get(legacy))
        assertEquals(2, attempts)
    }
}
