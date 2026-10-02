package io.github.xgl34222220.luoshu.ui.home

import io.github.xgl34222220.luoshu.ModuleSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HomeContractTest {
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
    fun liveRequestDoesNotReusePreviousMountFailureMessage() {
        for (taskState in listOf("running", "queued")) {
            val snapshot = ModuleSnapshot(
                installed = true,
                rootGranted = true,
                activeFont = "PreviousFont",
                effectiveFont = "default",
                fontEffectState = "failed",
                verificationReason = "physical-target-conflict",
                mountState = "failed",
                taskState = taskState,
                taskMessage = "正在准备当前字体任务",
                taskProgress = 14,
            )
            val state = snapshot.toHomeUiState()
            assertTrue(state.taskRunning)
            assertEquals("字体任务执行中", state.taskTitle)
            assertEquals("正在准备当前字体任务", state.taskMessage)
            assertEquals(14, state.taskProgress)
            assertEquals("系统默认字体（PreviousFont未生效）", state.currentFont)
            assertFalse(state.mountHealthy)
            assertTrue(snapshot.effectFailed)
            assertTrue(snapshot.effectFailureMessage.isNotBlank())

            // Finishing the new request must not turn an unverified mount green.
            val finished = snapshot.copy(taskState = "success").toHomeUiState()
            assertFalse(finished.taskRunning)
            assertEquals("字体未生效", finished.taskTitle)
            assertEquals(snapshot.effectFailureMessage, finished.taskMessage)
            assertFalse(finished.mountHealthy)
        }
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
    fun rollbackPendingShowsRecoveryTargetWithoutPretendingRollbackAlreadyHappened() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            activeFont = "BadUniversal",
            effectiveFont = "unknown",
            fontEffectState = "rollback-pending",
            verificationGrade = "FAIL",
            verificationReason = "coverage-digits-missing",
            mountState = "mounted",
            rollbackState = "staged",
            rollbackPending = true,
            rollbackTargetFont = "OldFont",
            rollbackTargetMode = "legacy",
            rebootRequired = true,
        ).toHomeUiState()

        assertEquals("BadUniversal（验证失败，待重启恢复 OldFont）", state.currentFont)
        assertEquals("正在等待安全回退", state.taskTitle)
        assertTrue(state.taskMessage.contains("OldFont"))
        assertTrue(state.taskMessage.contains("完整重启"))
        assertFalse(state.mountHealthy)
        assertTrue(state.rebootRequired)
    }

    @Test
    fun unresolvedUniversalFailureDoesNotPretendSystemDefaultIsAlreadyActive() {
        val state = ModuleSnapshot(
            loading = false,
            installed = true,
            rootGranted = true,
            activeFont = "BadUniversal",
            effectiveFont = "unknown",
            fontEffectState = "failed",
            verificationGrade = "FAIL",
            verificationMode = "universal-fail",
            verificationReason = "required-axis-missing",
            mountState = "mounted",
        ).toHomeUiState()

        assertEquals("BadUniversal（运行验证失败）", state.currentFont)
        assertEquals("字体未生效", state.taskTitle)
        assertTrue(state.taskMessage.contains("无法安全确认"))
        assertFalse(state.mountHealthy)
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
}
