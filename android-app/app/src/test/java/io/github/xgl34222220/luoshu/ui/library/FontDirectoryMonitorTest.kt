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

    private fun watched(path: String, size: Long, modified: Long): WatchedFontDocument = WatchedFontDocument(
        key = path,
        name = path.substringAfterLast('/'),
        uri = "content://fonts/$path",
        size = size,
        modified = modified,
    )
}
