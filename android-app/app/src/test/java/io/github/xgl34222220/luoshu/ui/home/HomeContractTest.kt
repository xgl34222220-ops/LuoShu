package io.github.xgl34222220.luoshu.ui.home

import io.github.xgl34222220.luoshu.ModuleSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeContractTest {
    @Test
    fun completedRootFailureShowsDisconnectedInsteadOfTheInitialDetectingLabel() {
        val state = ModuleSnapshot(loading = false, error = "未找到 Root 命令 su").toHomeUiState()

        assertFalse(state.loading)
        assertFalse(state.rootGranted)
        assertFalse(state.moduleInstalled)
        assertEquals("未连接", state.version)
        assertEquals("未找到 Root 命令 su", state.error)
    }

    @Test
    fun moduleMissingWithGrantedRootAlsoFinishesTheVersionCheck() {
        val state = ModuleSnapshot(loading = false, rootGranted = true, installed = false).toHomeUiState()

        assertFalse(state.loading)
        assertEquals("未连接", state.version)
    }

    @Test
    fun initialConnectionKeepsCheckingAndVerifiedConnectionKeepsItsRealVersion() {
        assertEquals("检测中…", ModuleSnapshot().toHomeUiState().version)
        val verified = ModuleSnapshot(loading = false, rootGranted = true, installed = true, version = "v2.2.2")
        assertEquals("v2.2.2", verified.toHomeUiState().version)
    }

    @Test
    fun failedMountShowsSystemFontInsteadOfConfiguredFontAsEffective() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            activeFont = "DemoFont",
            effectiveFont = "default",
            fontEffectState = "failed",
            verificationReason = "self-mount-not-visible",
            mountState = "failed",
            taskState = "success",
            taskMessage = "字体已准备",
        ).toHomeUiState()

        assertEquals("系统默认字体（DemoFont未生效）", state.currentFont)
        assertEquals("字体未生效", state.taskTitle)
        assertTrue(state.taskMessage.contains("默认字体"))
        assertFalse(state.mountHealthy)
    }

    @Test
    fun verifiedMountShowsConfiguredFontAsEffective() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            activeFont = "DemoFont",
            effectiveFont = "DemoFont",
            fontEffectState = "verified",
            mountState = "mounted",
        ).toHomeUiState()

        assertEquals("DemoFont", state.currentFont)
        assertEquals("字体引擎已就绪", state.taskTitle)
        assertTrue(state.mountHealthy)
    }

    @Test
    fun pendingRebootDoesNotPretendTheFontIsAlreadyEffective() {
        val state = ModuleSnapshot(
            loading = false,
            activeFont = "DemoFont",
            effectiveFont = "unknown",
            fontEffectState = "pending-reboot",
            rebootRequired = true,
        ).toHomeUiState()

        assertEquals("DemoFont（等待完整重启）", state.currentFont)
    }

    @Test
    fun dynamicConfigFailureProvidesAnActionableReason() {
        val state = ModuleSnapshot(
            loading = false,
            activeFont = "DemoFont",
            effectiveFont = "default",
            fontEffectState = "failed",
            verificationReason = "dynamic-config-overridden",
            mountState = "mounted",
        ).toHomeUiState()

        assertTrue(state.taskMessage.contains("动态字体配置"))
        assertTrue(state.taskMessage.contains("系统字体"))
    }

    @Test
    fun cachedSnapshotShowsPreviousFontWithoutAuthorizingRootActions() {
        val state = ModuleSnapshot(
            loading = false,
            statusCached = true,
            installed = true,
            rootGranted = true,
            rootManager = "Magisk",
            activeFont = "DemoFont",
            effectiveFont = "DemoFont",
            fontEffectState = "verified",
            mountState = "mounted",
            rebootRequired = true,
            liveApplied = true,
        ).toHomeUiState()

        assertTrue(state.loading)
        assertTrue(state.statusCached)
        assertEquals("DemoFont（上次记录，正在核实）", state.currentFont)
        assertEquals("正在核实模块状态", state.taskTitle)
        assertFalse(state.rootGranted)
        assertFalse(state.moduleInstalled)
        assertFalse(state.mountHealthy)
        assertFalse(state.rebootRequired)
        assertFalse(state.liveApplied)
    }

    @Test
    fun cachedCompositeFontUsesTheReadablePreviousLabel() {
        val state = ModuleSnapshot(statusCached = true, activeFont = "mix").toHomeUiState()

        assertEquals("完整复合字体（上次记录，正在核实）", state.currentFont)
    }

    @Test
    fun waitingCleanupRemainsBusyEvenWhenFontGenerationIsFinished() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            taskState = "waiting-cleanup",
            taskMessage = "任务进程尚未确认退出",
            taskProgress = 100,
        ).toHomeUiState()

        assertTrue(state.taskRunning)
        assertEquals("等待字体任务清理", state.taskTitle)
        assertEquals("任务进程尚未确认退出", state.taskMessage)
    }

    @Test
    fun loadingCannotAuthorizeRootActionsFromThePreviousSnapshot() {
        val state = ModuleSnapshot(
            loading = true,
            installed = true,
            rootGranted = true,
            mountState = "mounted",
            rebootRequired = true,
        ).toHomeUiState()

        assertTrue(state.loading)
        assertFalse(state.rootGranted)
        assertFalse(state.moduleInstalled)
        assertFalse(state.mountHealthy)
        assertFalse(state.rebootRequired)
    }

    @Test
    fun canonicalCleanupPendingStateRemainsBusy() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            taskState = "cleanup-pending",
            taskMessage = "等待确认任务进程全部退出",
            taskProgress = 100,
        ).toHomeUiState()

        assertTrue(state.taskRunning)
        assertEquals("等待字体任务清理", state.taskTitle)
        assertEquals("等待确认任务进程全部退出", state.taskMessage)
    }

    @Test
    fun liveMountPreservesBothCurrentBootAndFullRebootStatus() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            activeFont = "DemoFont",
            effectiveFont = "DemoFont",
            fontEffectState = "live-mounted",
            liveApplied = true,
            rebootRequired = true,
            mountState = "mounted",
        ).toHomeUiState()

        assertTrue(state.liveApplied)
        assertTrue(state.rebootRequired)
        assertTrue(state.mountHealthy)
        assertEquals("DemoFont（当前启动已挂载，重启后完整生效）", state.currentFont)
        assertFalse(state.taskRunning)
    }
}
