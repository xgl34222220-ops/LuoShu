package io.github.xgl34222220.luoshu.ui.home

import io.github.xgl34222220.luoshu.ModuleSnapshot
import io.github.xgl34222220.luoshu.SystemWeightState
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
        ).toHomeUiState(SystemWeightState())

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
        ).toHomeUiState(SystemWeightState())

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
        ).toHomeUiState(SystemWeightState())

        assertEquals("DemoFont（等待重启）", state.currentFont)
    }
}
