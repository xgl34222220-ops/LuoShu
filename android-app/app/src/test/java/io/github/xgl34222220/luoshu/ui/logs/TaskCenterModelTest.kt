package io.github.xgl34222220.luoshu.ui.logs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskCenterModelTest {
    @Test
    fun structuredLogsBecomeNewestFirstTaskTimeline() {
        val tasks = parseTaskLogItems(
            """
            [2026-07-19 15:00:00] [INFO] 开始扫描字体库
            [2026-07-19 15:01:00] [INFO] 字体导入完成，成功导入 2 个文件
            [2026-07-19 15:02:00] [ERROR] 复合字体生成失败
            """.trimIndent(),
        )

        assertEquals(3, tasks.size)
        assertEquals(TaskKind.MIX, tasks[0].kind)
        assertEquals(TaskPhase.FAILED, tasks[0].phase)
        assertEquals(TaskKind.IMPORT, tasks[1].kind)
        assertEquals(TaskPhase.SUCCESS, tasks[1].phase)
        assertEquals(TaskKind.SCAN, tasks[2].kind)
        assertEquals(TaskPhase.RUNNING, tasks[2].phase)
    }

    @Test
    fun rebootMessagesUseWaitingRebootPhase() {
        assertEquals(
            TaskPhase.WAITING_REBOOT,
            taskPhaseFor("INFO", "字体已准备完成，完整重启后全局生效"),
        )
    }

    @Test
    fun currentTaskWinsWhenHistoryContainsSameMessage() {
        val current = TaskCenterItem(
            id = "current",
            kind = TaskKind.APPLY,
            phase = TaskPhase.RUNNING,
            title = "字体应用进行中",
            message = "正在验证并应用字体",
            current = true,
        )
        val duplicateHistory = current.copy(id = "history", current = false)
        val merged = mergeTaskItems(listOf(current), listOf(duplicateHistory))

        assertEquals(1, merged.size)
        assertTrue(merged.single().current)
    }

    @Test
    fun progressIsReadFromLogMessage() {
        val task = parseTaskLogItems(
            "[2026-07-19 15:03:00] [INFO] 复合字体正在生成 68%",
        ).single()

        assertEquals(TaskKind.MIX, task.kind)
        assertEquals(TaskPhase.RUNNING, task.phase)
        assertEquals(68, task.progress)
    }

    @Test
    fun internalMixStagesDoNotBecomeMultipleRunningTasks() {
        val tasks = parseTaskLogItems(
            """
            [2026-07-22 19:02:40] mix stage=initialize percent=1 message=正在初始化字体组合任务
            [2026-07-22 19:02:45] mix stage=mapping percent=91 message=正在生成系统字体映射
            [2026-07-22 19:02:50] mix stage=mount-sync percent=96 message=正在同步元模块字体负载
            """.trimIndent(),
        )

        assertTrue(tasks.isEmpty())
    }
}
