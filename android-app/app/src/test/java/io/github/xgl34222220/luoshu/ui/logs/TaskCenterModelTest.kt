package io.github.xgl34222220.luoshu.ui.logs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TaskCenterModelTest {
    @Test
    fun serviceTemplateErrorDoesNotInventAUserApplyFailure() {
        val task = parseTaskLogItems(
            "[2026-10-07 20:49:13] [SERVICE] [ERROR] 原厂字体槽位模板刷新失败；明确应用会保持旧负载并返回错误",
        ).single()
        assertEquals(TaskKind.TEMPLATE, task.kind)
        assertEquals(TaskPhase.FAILED, task.phase)
        assertEquals("原厂槽位检查失败", task.title)
        assertFalse(task.completed)
    }

    @Test
    fun awaitingMountConfirmationIsNotACompletedReboot() {
        val task = parseTaskLogItems(
            "[1970-10-07 13:05:33] [INFO] 当前文字=mix | 等待主命名空间挂载确认后完成重启事务",
        ).single()
        assertEquals(TaskKind.REBOOT, task.kind)
        assertEquals(TaskPhase.WAITING_CONFIRMATION, task.phase)
        assertEquals("设备重启等待挂载确认", task.title)
        assertEquals("开机早期，时间未同步", task.timeLabel)
        assertFalse(task.completed)
        assertFalse(task.active)
    }

    @Test
    fun actualApplyFailuresAndConfirmedRebootsKeepTheirOutcome() {
        assertEquals(TaskKind.APPLY, taskKindFor("字体应用失败：负载校验错误"))
        assertEquals(TaskKind.APPLY, taskKindFor("字体应用失败：原厂模板不可用"))
        assertEquals(TaskKind.APPLY, taskKindFor("原厂模板不可用", "switch"))
        assertEquals(TaskKind.MIX, taskKindFor("原厂模板不可用", "mix"))
        assertEquals(TaskPhase.FAILED, taskPhaseFor("ERROR", "字体应用失败：负载校验错误"))
        assertEquals(TaskPhase.SUCCESS, taskPhaseFor("INFO", "设备重启已完成，主命名空间挂载确认成功"))
    }

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

    @Test
    fun failedFontWorkStillCountsAsActiveUntilCleanupIsConfirmed() {
        val phase = taskPhaseFor("ERROR", "复合字体生成失败，后台任务清理尚未确认", "cleanup-pending")
        val task = TaskCenterItem(
            id = "owned-font", kind = TaskKind.MIX, phase = phase,
            title = taskTitle(TaskKind.MIX, phase), message = "后台任务清理尚未确认", current = true,
        )

        assertEquals(TaskPhase.WAITING_CLEANUP, task.phase)
        assertEquals("等待清理", task.phase.label)
        assertEquals("字体组合等待清理", task.title)
        assertTrue(task.active)
        assertFalse(task.completed)
        assertEquals(1, mergeTaskItems(listOf(task), emptyList()).count { it.active })
    }

    @Test
    fun pendingCleanupOverridesOldSuccessAndRebootMessages() {
        val phase = taskPhaseFor("INFO", "字体已准备完成，完整重启后生效", "cleanup-pending")
        assertEquals(TaskPhase.WAITING_CLEANUP, phase)
    }

    @Test
    fun confirmedTerminalResultsRemoveThePendingTaskFromActiveCount() {
        val pending = TaskCenterItem(
            id = "owned-font", kind = TaskKind.APPLY, phase = TaskPhase.WAITING_CLEANUP,
            title = "字体应用等待清理", message = "后台任务清理尚未确认", current = true,
        )
        val cancelled = pending.copy(
            phase = taskPhaseFor("INFO", "字体任务已取消，后台进程已清理", "cancelled"),
            message = "字体任务已取消，后台进程已清理",
        )
        assertEquals(TaskPhase.INFO, cancelled.phase)
        assertFalse(cancelled.active)
        assertEquals(0, mergeTaskItems(listOf(cancelled), emptyList()).count { it.active })
        assertFalse(pending.copy(phase = TaskPhase.FAILED).active)
        assertFalse(pending.copy(phase = TaskPhase.SUCCESS).active)
    }
}
