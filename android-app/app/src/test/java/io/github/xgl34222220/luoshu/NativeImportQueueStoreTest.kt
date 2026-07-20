package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportQueueStoreTest {
    @Test
    fun queueRoundTripPreservesNamesUrisAndResults() {
        val task = ImportQueueTask(
            taskId = "import-12345",
            phase = NativeImportPhase.RUNNING,
            createdAt = 12345L,
            message = "正在导入 中文字体.ttf",
            items = listOf(
                ImportQueueItem(
                    uri = "content://documents/中文字体.ttf",
                    displayName = "中文字体.ttf",
                    status = ImportQueueItemStatus.IMPORTED,
                    persistedPermission = true,
                ),
                ImportQueueItem(
                    uri = "content://documents/latin.zip",
                    displayName = "latin.zip",
                    status = ImportQueueItemStatus.RUNNING,
                    persistedPermission = true,
                ),
            ),
        )

        val decoded = decodeImportQueue(encodeImportQueue(task))

        assertNotNull(decoded)
        assertEquals(task.taskId, decoded?.taskId)
        assertEquals(task.message, decoded?.message)
        assertEquals("中文字体.ttf", decoded?.items?.first()?.displayName)
        assertEquals("content://documents/中文字体.ttf", decoded?.items?.first()?.uri)
        assertEquals(ImportQueueItemStatus.RUNNING, decoded?.items?.last()?.status)
        assertTrue(decoded?.items?.all { it.persistedPermission } == true)
    }

    @Test
    fun resumeOnlyResetsInterruptedItem() {
        val task = ImportQueueTask(
            taskId = "import-67890",
            phase = NativeImportPhase.RUNNING,
            createdAt = 67890L,
            message = "处理中",
            items = listOf(
                ImportQueueItem("content://one", "one.ttf", ImportQueueItemStatus.IMPORTED),
                ImportQueueItem("content://two", "two.ttf", ImportQueueItemStatus.DUPLICATE),
                ImportQueueItem("content://three", "three.ttf", ImportQueueItemStatus.RUNNING),
                ImportQueueItem("content://four", "four.ttf", ImportQueueItemStatus.PENDING),
            ),
        )

        val resumed = task.forResume()

        assertEquals(NativeImportPhase.QUEUED, resumed.phase)
        assertTrue(resumed.recovered)
        assertEquals(ImportQueueItemStatus.IMPORTED, resumed.items[0].status)
        assertEquals(ImportQueueItemStatus.DUPLICATE, resumed.items[1].status)
        assertEquals(ImportQueueItemStatus.PENDING, resumed.items[2].status)
        assertEquals(ImportQueueItemStatus.PENDING, resumed.items[3].status)
        assertEquals(2, resumed.processed)
        assertEquals(1, resumed.imported)
        assertEquals(1, resumed.duplicates)
    }

    @Test
    fun terminalQueueRestoresAsNonBusyUiState() {
        val task = ImportQueueTask(
            taskId = "import-complete",
            phase = NativeImportPhase.SUCCESS,
            createdAt = 1L,
            message = "字体导入完成，共处理 1 个文件",
            items = listOf(
                ImportQueueItem("content://one", "one.ttf", ImportQueueItemStatus.IMPORTED),
            ),
        )

        val state = task.toUiState()

        assertFalse(state.busy)
        assertEquals(100, state.progress)
        assertEquals(1, state.imported)
        assertEquals("导入完成", state.title)
    }
}
