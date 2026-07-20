package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportControlsTest {
    @Test
    fun pausedStateExposesResumeCancelAndClear() {
        val state = NativeImportState(
            taskId = "import-paused",
            phase = NativeImportPhase.PAUSED,
            total = 4,
            processed = 2,
            imported = 1,
            duplicates = 1,
            message = "导入已暂停",
        )

        assertFalse(state.busy)
        assertTrue(state.paused)
        assertFalse(state.canPause)
        assertTrue(state.canResume)
        assertTrue(state.canCancel)
        assertTrue(state.canClear)
        assertEquals(50, state.progress)
        assertEquals("字体导入已暂停", state.title)
    }

    @Test
    fun cancelRemainingKeepsFinishedItemsAndStopsOnlyPendingWork() {
        val task = ImportQueueTask(
            taskId = "import-cancel",
            phase = NativeImportPhase.RUNNING,
            createdAt = 1L,
            message = "处理中",
            items = listOf(
                ImportQueueItem("content://one", "one.ttf", ImportQueueItemStatus.IMPORTED),
                ImportQueueItem("content://two", "two.ttf", ImportQueueItemStatus.DUPLICATE),
                ImportQueueItem("content://three", "three.ttf", ImportQueueItemStatus.FAILED, "字体损坏"),
                ImportQueueItem("content://four", "four.ttf", ImportQueueItemStatus.RUNNING),
                ImportQueueItem("content://five", "five.ttf", ImportQueueItemStatus.PENDING),
            ),
        )

        val cancelled = task.cancelRemaining()

        assertEquals(NativeImportPhase.CANCELLED, cancelled.phase)
        assertEquals(ImportQueueItemStatus.IMPORTED, cancelled.items[0].status)
        assertEquals(ImportQueueItemStatus.DUPLICATE, cancelled.items[1].status)
        assertEquals(ImportQueueItemStatus.FAILED, cancelled.items[2].status)
        assertEquals(ImportQueueItemStatus.CANCELLED, cancelled.items[3].status)
        assertEquals(ImportQueueItemStatus.CANCELLED, cancelled.items[4].status)
        assertEquals(2, cancelled.cancelled)
        assertEquals(5, cancelled.processed)
        assertTrue(cancelled.failures.single().contains("字体损坏"))
    }

    @Test
    fun retryFailuresResetsOnlyFailedItems() {
        val task = ImportQueueTask(
            taskId = "import-retry",
            phase = NativeImportPhase.FAILED,
            createdAt = 1L,
            message = "部分失败",
            items = listOf(
                ImportQueueItem("content://one", "one.ttf", ImportQueueItemStatus.IMPORTED),
                ImportQueueItem("content://two", "two.ttf", ImportQueueItemStatus.DUPLICATE),
                ImportQueueItem("content://three", "three.ttf", ImportQueueItemStatus.FAILED, "无法读取"),
                ImportQueueItem("content://four", "four.ttf", ImportQueueItemStatus.CANCELLED),
            ),
        )

        val retried = task.forRetryFailures()

        assertEquals(NativeImportPhase.QUEUED, retried.phase)
        assertEquals(ImportQueueItemStatus.IMPORTED, retried.items[0].status)
        assertEquals(ImportQueueItemStatus.DUPLICATE, retried.items[1].status)
        assertEquals(ImportQueueItemStatus.PENDING, retried.items[2].status)
        assertEquals("", retried.items[2].error)
        assertEquals(ImportQueueItemStatus.CANCELLED, retried.items[3].status)
        assertEquals(3, retried.processed)
    }

    @Test
    fun cancelledStateReportsCancelledCountWithoutBecomingBusy() {
        val state = NativeImportState(
            taskId = "import-cancelled",
            phase = NativeImportPhase.CANCELLED,
            total = 5,
            processed = 5,
            imported = 2,
            duplicates = 1,
            cancelled = 2,
            message = "字体导入已取消",
        )

        assertFalse(state.busy)
        assertTrue(state.terminal)
        assertTrue(state.canClear)
        assertEquals("字体导入已取消", state.title)
        assertTrue(state.summary.contains("已处理 3/5 个文件"))
        assertTrue(state.summary.contains("取消 2 个待处理文件"))
    }
}
