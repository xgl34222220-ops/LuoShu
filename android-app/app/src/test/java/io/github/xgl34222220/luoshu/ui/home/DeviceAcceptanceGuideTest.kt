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
    fun compatibilityWithoutLoadEvidenceDoesNotPassAcceptance() {
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

        val reboot = checks.first { it.id == "reboot" }
        val alignment = checks.first { it.id == "alignment" }
        val cache = checks.first { it.id == "cache" }

        assertFalse(reboot.passed)
        assertFalse(reboot.blocking)
        assertFalse(alignment.passed)
        assertFalse(alignment.blocking)
        assertFalse(cache.passed)
        assertFalse(cache.blocking)
    }
}
