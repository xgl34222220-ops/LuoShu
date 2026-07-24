package io.github.xgl34222220.luoshu.ui.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceAcceptanceGuideTest {
    @Test
    fun verifiedAlignedDevicePassesAutomaticChecks() {
        val checks = deviceAcceptanceAutoChecks(
            state = HomeUiState(
                rootGranted = true,
                moduleInstalled = true,
                taskRunning = false,
                rebootRequired = false,
            ),
            trust = DeviceTrustState(
                loading = false,
                inventory = "available",
                engine = "ready",
                template = "trusted",
                alignment = "verified",
                mode = "aligned",
                cachePending = false,
            ),
        )

        assertEquals(6, checks.size)
        assertTrue(checks.all { it.automatic && it.passed })
    }

    @Test
    fun pendingRebootBlocksAcceptance() {
        val checks = deviceAcceptanceAutoChecks(
            state = HomeUiState(
                rootGranted = true,
                moduleInstalled = true,
                rebootRequired = true,
            ),
            trust = DeviceTrustState(
                loading = false,
                inventory = "available",
                alignment = "pending",
                mode = "compatibility",
                cachePending = true,
            ),
        )

        assertFalse(checks.first { it.id == "reboot" }.passed)
        assertFalse(checks.first { it.id == "alignment" }.passed)
        assertFalse(checks.first { it.id == "cache" }.passed)
    }
}
