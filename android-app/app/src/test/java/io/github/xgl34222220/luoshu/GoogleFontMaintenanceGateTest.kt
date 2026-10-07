package io.github.xgl34222220.luoshu

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GoogleFontMaintenanceGateTest {
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
