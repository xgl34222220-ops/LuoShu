package io.github.xgl34222220.luoshu

import io.github.xgl34222220.luoshu.ui.logs.LogsUiState
import io.github.xgl34222220.luoshu.ui.logs.TaskKind
import io.github.xgl34222220.luoshu.ui.logs.TaskPhase
import io.github.xgl34222220.luoshu.ui.logs.withNativeImport
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportTaskCenterTest {
    @Test
    fun recoveredImportAppearsBeforeHistoryAsActiveTask() {
        val display = LogsUiState().withNativeImport(
            NativeImportState(
                taskId = "import-resume",
                phase = NativeImportPhase.RUNNING,
                total = 4,
                processed = 2,
                currentFile = "third.ttf",
                message = "正在恢复 3/4：third.ttf",
                recovered = true,
            ),
        )

        assertEquals(1, display.activeTaskCount)
        assertTrue(display.tasks.isNotEmpty())
        assertEquals(TaskKind.IMPORT, display.tasks.first().kind)
        assertEquals(TaskPhase.RUNNING, display.tasks.first().phase)
        assertTrue(display.tasks.first().message.contains("恢复"))
    }
}
