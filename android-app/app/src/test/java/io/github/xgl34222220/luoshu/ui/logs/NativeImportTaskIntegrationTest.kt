package io.github.xgl34222220.luoshu.ui.logs

import io.github.xgl34222220.luoshu.NativeImportPhase
import io.github.xgl34222220.luoshu.NativeImportState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportTaskIntegrationTest {
    @Test
    fun runningImportAppearsBeforeHistoryAndUpdatesActiveCount() {
        val history = TaskCenterItem(
            id = "old-scan",
            kind = TaskKind.SCAN,
            phase = TaskPhase.SUCCESS,
            title = "字体扫描已完成",
            message = "字体索引已更新",
        )
        val result = LogsUiState(tasks = listOf(history)).withNativeImport(
            NativeImportState(
                taskId = "import-1",
                phase = NativeImportPhase.RUNNING,
                total = 4,
                processed = 2,
                currentFile = "Example.ttf",
                message = "正在导入 3/4：Example.ttf",
            ),
        )

        assertEquals(TaskKind.IMPORT, result.tasks.first().kind)
        assertEquals(TaskPhase.RUNNING, result.tasks.first().phase)
        assertEquals(50, result.tasks.first().progress)
        assertEquals(1, result.activeTaskCount)
    }

    @Test
    fun failedImportUpdatesFailureCount() {
        val result = LogsUiState().withNativeImport(
            NativeImportState(
                taskId = "import-2",
                phase = NativeImportPhase.FAILED,
                total = 1,
                processed = 1,
                failed = listOf("bad.ttf：字体不可用"),
                message = "字体导入失败，未成功处理任何文件",
            ),
        )

        assertEquals(1, result.failedTaskCount)
        assertEquals(0, result.activeTaskCount)
        assertTrue(result.tasks.first().message.contains("失败"))
    }

    @Test
    fun successfulImportCountsAsCompleted() {
        val result = LogsUiState().withNativeImport(
            NativeImportState(
                taskId = "import-3",
                phase = NativeImportPhase.SUCCESS,
                total = 2,
                processed = 2,
                imported = 2,
                message = "字体导入完成，共处理 2 个文件",
            ),
        )

        assertEquals(1, result.completedTaskCount)
        assertEquals(TaskPhase.SUCCESS, result.tasks.first().phase)
    }
}
