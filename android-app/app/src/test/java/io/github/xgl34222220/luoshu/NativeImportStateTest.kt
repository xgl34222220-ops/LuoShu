package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportStateTest {
    @Test
    fun runningStateCalculatesProgressBelowCompletion() {
        val state = NativeImportState(
            phase = NativeImportPhase.RUNNING,
            total = 3,
            processed = 2,
            currentFile = "Example.ttf",
        )

        assertTrue(state.busy)
        assertEquals(66, state.progress)
        assertEquals("正在导入字体", state.title)
    }

    @Test
    fun completedStateReportsImportedAndDuplicates() {
        val state = NativeImportState(
            phase = NativeImportPhase.SUCCESS,
            total = 4,
            processed = 4,
            imported = 3,
            duplicates = 1,
        )

        assertFalse(state.busy)
        assertEquals(100, state.progress)
        assertEquals("导入完成", state.title)
        assertTrue(state.summary.contains("成功导入 3 个文件"))
        assertTrue(state.summary.contains("跳过 1 个重复字体"))
    }

    @Test
    fun partialFailureKeepsSuccessfulCountsVisible() {
        val state = NativeImportState(
            phase = NativeImportPhase.FAILED,
            total = 3,
            processed = 3,
            imported = 1,
            duplicates = 1,
            failed = listOf("broken.ttf：字体文件不可用"),
        )

        assertEquals("导入部分完成", state.title)
        assertTrue(state.summary.contains("成功导入 1 个文件"))
        assertTrue(state.summary.contains("broken.ttf"))
    }

    @Test
    fun totalFailureUsesFailureTitle() {
        val state = NativeImportState(
            phase = NativeImportPhase.FAILED,
            total = 1,
            processed = 1,
            failed = listOf("bad.zip：ZIP 中没有字体文件"),
        )

        assertEquals("导入失败", state.title)
        assertEquals(100, state.progress)
    }
}
