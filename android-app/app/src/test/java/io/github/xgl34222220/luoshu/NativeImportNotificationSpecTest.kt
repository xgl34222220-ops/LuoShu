package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportNotificationSpecTest {
    @Test
    fun runningNotificationOffersPauseAndCancel() {
        val spec = nativeImportNotificationSpec(
            NativeImportState(
                phase = NativeImportPhase.RUNNING,
                total = 4,
                processed = 1,
                message = "正在导入 2/4：font.ttf",
            ),
        )

        assertTrue(spec.ongoing)
        assertEquals(4, spec.total)
        assertEquals(1, spec.processed)
        assertEquals(
            listOf(NativeImportNotificationAction.PAUSE, NativeImportNotificationAction.CANCEL),
            spec.actions,
        )
    }

    @Test
    fun pausedNotificationOffersResumeAndCancel() {
        val spec = nativeImportNotificationSpec(
            NativeImportState(
                phase = NativeImportPhase.PAUSED,
                total = 3,
                processed = 1,
                message = "导入已暂停",
            ),
        )

        assertFalse(spec.ongoing)
        assertEquals(
            listOf(NativeImportNotificationAction.RESUME, NativeImportNotificationAction.CANCEL),
            spec.actions,
        )
    }

    @Test
    fun failedNotificationOffersRetryAndClear() {
        val spec = nativeImportNotificationSpec(
            NativeImportState(
                phase = NativeImportPhase.FAILED,
                total = 2,
                processed = 2,
                failed = listOf("broken.ttf：字体文件不可用"),
                message = "字体导入失败",
            ),
        )

        assertEquals(
            listOf(NativeImportNotificationAction.RETRY, NativeImportNotificationAction.CLEAR),
            spec.actions,
        )
    }

    @Test
    fun successfulNotificationOnlyOffersClear() {
        val spec = nativeImportNotificationSpec(
            NativeImportState(
                phase = NativeImportPhase.SUCCESS,
                total = 1,
                processed = 1,
                imported = 1,
                message = "字体导入完成",
            ),
        )

        assertEquals(listOf(NativeImportNotificationAction.CLEAR), spec.actions)
    }
}
