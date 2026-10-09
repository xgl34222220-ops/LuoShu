package io.github.xgl34222220.luoshu.ui.library

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FontDirectoryMonitorTest {
    @Test
    fun snapshotDiffSeparatesAddedChangedAndRemovedDocuments() {
        val previous = listOf(
            watched("a.ttf", size = 100, modified = 1),
            watched("b.otf", size = 200, modified = 2),
            watched("removed.ttc", size = 300, modified = 3),
        ).associateBy { it.key }
        val current = listOf(
            watched("a.ttf", size = 100, modified = 1),
            watched("b.otf", size = 220, modified = 4),
            watched("new.zip", size = 400, modified = 5),
        )

        val diff = diffFontDirectorySnapshots(previous, current)

        assertEquals(listOf("new.zip"), diff.added.map { it.key })
        assertEquals(listOf("b.otf"), diff.changed.map { it.key })
        assertEquals(listOf("removed.ttc"), diff.removed.map { it.key })
        assertEquals(listOf("new.zip", "b.otf"), diff.actionable.map { it.key })
        assertTrue(diff.hasChanges)
    }

    @Test
    fun identicalSnapshotsHaveNoChanges() {
        val document = watched("fonts/main.ttf", size = 1024, modified = 99)
        val diff = diffFontDirectorySnapshots(mapOf(document.key to document), listOf(document))

        assertFalse(diff.hasChanges)
        assertTrue(diff.actionable.isEmpty())
    }

    @Test
    fun everyPendingDocumentCanBeSelectedWithoutChangingTheBaseline() {
        val previous = mapOf("old.ttf" to watched("old.ttf", size = 100, modified = 1))
        val current = (1..70).map { watched("new-$it.ttf", size = it.toLong(), modified = 2) }
        val pending = diffFontDirectorySnapshots(previous, current).actionable

        assertEquals(3, fontDirectoryImportBatchCount(pending))
        val batches = (0..2).map { fontDirectoryImportBatch(pending, it) }
        assertEquals(listOf(32, 32, 6), batches.map { it.size })
        assertEquals(pending, batches.flatten())
        assertEquals(listOf("old.ttf"), previous.keys.toList())
        assertEquals(pending, diffFontDirectorySnapshots(previous, current).actionable)
    }

    @Test
    fun repeatedBatchSelectionKeepsFailedOrCancelledDocumentsAvailable() {
        val pending = (1..40).map { watched("new-$it.ttf", size = it.toLong(), modified = 2) }

        val firstRequest = fontDirectoryImportBatch(pending, 0)
        val retry = fontDirectoryImportBatch(pending, 0)
        val remaining = fontDirectoryImportBatch(pending, 1)

        assertEquals(firstRequest, retry)
        assertEquals(32, retry.size)
        assertEquals(pending.drop(32), remaining)
        assertEquals(40, pending.size)
    }

    @Test
    fun emptyAndExactBatchBoundariesDoNotOfferAnExtraBatch() {
        assertEquals(0, fontDirectoryImportBatchCount(emptyList()))
        assertTrue(fontDirectoryImportBatch(emptyList(), 1).isEmpty())
        val pending = (1..64).map { watched("new-$it.ttf", size = it.toLong(), modified = 2) }
        assertEquals(2, fontDirectoryImportBatchCount(pending))
        assertEquals(pending.take(32), fontDirectoryImportBatch(pending, -1))
        assertEquals(pending.drop(32), fontDirectoryImportBatch(pending, 99))
    }

    @Test
    fun replacingASlowScanRejectsItsResultAndItsCleanup() {
        val requests = FontDirectoryScanRequests()
        val old = requests.start("content://tree/a")
        val latest = requests.start("content://tree/b")

        assertFalse(requests.isCurrent(old, "content://tree/b"))
        assertFalse(requests.isCurrent(old, "content://tree/a"))
        assertTrue(requests.isCurrent(latest, "content://tree/b"))
    }

    @Test
    fun disconnectAndSameUriReconnectDoNotReviveTheOldRequest() {
        val requests = FontDirectoryScanRequests()
        val old = requests.start("content://tree/a")
        requests.invalidate()
        assertFalse(requests.isCurrent(old, "content://tree/a"))

        val reconnect = requests.start("content://tree/a")
        assertFalse(requests.isCurrent(old, "content://tree/a"))
        assertTrue(requests.isCurrent(reconnect, "content://tree/a"))
    }

    @Test
    fun repeatedScanOfTheSameTreeAcceptsOnlyTheLatestRequest() {
        val requests = FontDirectoryScanRequests()
        val first = requests.start("content://tree/a")
        val second = requests.start("content://tree/a")
        val latest = requests.start("content://tree/a")

        assertFalse(requests.isCurrent(first, "content://tree/a"))
        assertFalse(requests.isCurrent(second, "content://tree/a"))
        assertTrue(requests.isCurrent(latest, "content://tree/a"))
        assertFalse(requests.isCurrent(latest, "content://tree/b"))
    }

    private fun watched(path: String, size: Long, modified: Long): WatchedFontDocument = WatchedFontDocument(
        key = path,
        name = path.substringAfterLast('/'),
        uri = "content://fonts/$path",
        size = size,
        modified = modified,
    )
}
