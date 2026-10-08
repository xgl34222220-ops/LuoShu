package io.github.xgl34222220.luoshu

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GoogleFontMaintenanceGateTest {
    @Test fun onlyFreshRootInstalledAndExplicitlyEnabledStatusAllowsMaintenance() {
        for (bits in 0 until 32) {
            val loading = bits and 1 != 0
            val cached = bits and 2 != 0
            val root = bits and 4 != 0
            val installed = bits and 8 != 0
            val enabled = bits and 16 != 0
            val eligible = googleFontMaintenanceEligible(loading, cached, root, installed, enabled)
            val gate = GoogleFontMaintenanceGate()
            if (bits == 28) {
                assertTrue(eligible)
                assertTrue(gate.update(eligible, resumed = true))
            } else {
                assertFalse(eligible)
                assertFalse(gate.update(eligible, resumed = true))
                assertFalse(gate.packageReplaced())
                assertFalse(gate.completed())
            }
        }
        assertFalse(googleFontMaintenanceEligible(false, false, true, true))
    }

    @Test fun disablingModuleDuringMaintenanceDiscardsQueuedUpgradeWork() {
        val gate = GoogleFontMaintenanceGate()
        assertTrue(gate.update(googleFontMaintenanceEligible(false, false, true, true, true), true))
        assertFalse(gate.packageReplaced())
        assertFalse(gate.update(googleFontMaintenanceEligible(false, false, true, true, false), true))
        assertFalse(gate.packageReplaced())
        assertFalse(gate.completed())
    }

    @Test fun noRootOrCachedSnapshotNeverSchedulesARequestOrPackageRetry() {
        val gate = GoogleFontMaintenanceGate()
        assertFalse(gate.update(trusted = false, resumed = true))
        assertFalse(gate.packageReplaced())
        assertFalse(gate.completed())
        assertTrue(gate.update(trusted = true, resumed = true))
    }

    @Test fun firstVerifiedForegroundSnapshotRunsOnlyOncePerResume() {
        val gate = GoogleFontMaintenanceGate()
        assertFalse(gate.update(trusted = false, resumed = true))
        assertTrue(gate.update(trusted = true, resumed = true))
        assertFalse(gate.update(trusted = true, resumed = true))
        assertFalse(gate.completed())
        assertFalse(gate.update(trusted = true, resumed = true))
        assertFalse(gate.update(trusted = true, resumed = false))
        assertTrue(gate.update(trusted = true, resumed = true))
    }

    @Test fun concurrentUpgradeEventsAreMergedAndDoNotStartParallelRequests() {
        val gate = GoogleFontMaintenanceGate()
        assertTrue(gate.update(trusted = true, resumed = true))
        repeat(5) { assertFalse(gate.packageReplaced()) }
        assertTrue(gate.completed())
        assertFalse(gate.completed())
    }

    @Test fun losingTrustedModuleStateDiscardsPendingPackageWork() {
        val gate = GoogleFontMaintenanceGate()
        assertTrue(gate.update(trusted = true, resumed = true))
        assertFalse(gate.packageReplaced())
        assertFalse(gate.update(trusted = false, resumed = true))
        assertFalse(gate.completed())
        assertFalse(gate.update(trusted = true, resumed = true))
    }

    @Test fun trustedBackgroundPackageEventRequiresNoResidentLoop() {
        val gate = GoogleFontMaintenanceGate()
        assertFalse(gate.update(trusted = true, resumed = false))
        assertTrue(gate.packageReplaced())
        assertFalse(gate.completed())
    }

    @Test fun foregroundReturnDuringRunningWorkDoesNotRepeatSu() {
        val gate = GoogleFontMaintenanceGate()
        assertTrue(gate.update(trusted = true, resumed = true))
        repeat(5) {
            assertFalse(gate.update(trusted = true, resumed = false))
            assertFalse(gate.update(trusted = true, resumed = true))
        }
        assertFalse(gate.completed())
        assertFalse(gate.update(trusted = true, resumed = true))
        assertFalse(gate.update(trusted = true, resumed = false))
        assertTrue(gate.update(trusted = true, resumed = true))
        assertFalse(gate.completed())
    }

    @Test fun foregroundDuringAnExistingBackgroundUpgradePassIsAlreadyHandled() {
        val gate = GoogleFontMaintenanceGate()
        assertFalse(gate.update(trusted = true, resumed = false))
        assertTrue(gate.packageReplaced())
        assertFalse(gate.update(trusted = true, resumed = true))
        assertFalse(gate.completed())
        assertFalse(gate.update(trusted = true, resumed = true))
    }
}
