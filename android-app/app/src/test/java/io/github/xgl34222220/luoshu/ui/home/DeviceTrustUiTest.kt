package io.github.xgl34222220.luoshu.ui.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceTrustUiTest {
    @Test
    fun verifiedDeviceStateIsRecognized() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=verified
                mode=aligned
                reason=
                cachePending=no
            """.trimIndent(),
        )

        assertFalse(state.loading)
        assertEquals(DeviceTrustLevel.VERIFIED, state.level)
        assertEquals("trusted", state.template)
        assertFalse(state.cachePending)
    }

    @Test
    fun restoredSystemFontDoesNotPretendVerificationIsPending() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=default
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=not-applicable
                mode=compatibility
                reason=default-font
                cachePending=no
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.SYSTEM, state.level)
        assertEquals("default-font", state.reason)
    }

    @Test
    fun compatibilityMappingIsNotPresentedAsWaitingForReboot() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=ready
                template=trusted
                alignment=compatibility
                mode=compatibility
                reason=aligned-payload-not-active
                cachePending=no
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.COMPATIBILITY, state.level)
    }

    @Test
    fun installedEngineWithoutLoadEvidenceIsStillCompatibilityOnly() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=compatibility
                mode=compatibility
                reason=aligned-payload-not-active
                cachePending=no
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.COMPATIBILITY, state.level)
    }

    @Test
    fun failedAlignmentTakesPriorityForCustomFont() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=failed
                mode=compatibility
                reason=aligned-manifest-missing
                cachePending=yes
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
        assertTrue(state.cachePending)
    }

    @Test
    fun failedAtomicMountCannotBePresentedAsVerified() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=verified
                mode=mount-verified
                reason=
                mountState=failed
                cachePending=no
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
    }

    @Test
    fun currentBootPendingReasonIsNotDowngradedToCompatibility() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=pending
                mode=compatibility
                reason=stale-self-mount
                mountState=mounted
                cachePending=no
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.PENDING, state.level)
    }

    @Test
    fun dynamicConfigOverrideIsAlwaysAnIssue() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=failed
                mode=compatibility
                reason=dynamic-config-overridden
                mountState=mounted
                cachePending=no
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
    }

    @Test
    fun preservedUpgradeRequiresOneExplicitApplyEvenWithOldVerifiedRecord() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=verified
                mode=mount-verified
                reason=
                mountState=mounted
                cachePending=no
                reapplyPending=yes
                reapplyReason=schema-upgrade
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.PENDING, state.level)
        assertTrue(state.reapplyPending)
        assertEquals("schema-upgrade", state.reapplyReason)
    }

    @Test
    fun pendingStockInventoryReasonIsExposed() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
slotSnapshot=ready
slotCount=42
targetCount=36
                engine=installed
                template=trusted
                alignment=compatibility
                mode=compatibility
                reason=
                cachePending=no
                inventoryScanPending=yes
                inventoryScanReason=分区 /system/fonts 未找到可信原厂视图
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.PENDING, state.level)
        assertTrue(state.inventoryScanPending)
        assertEquals("分区 /system/fonts 未找到可信原厂视图", state.inventoryScanReason)
    }

    @Test
    fun flashTimeSlotSnapshotIsParsed() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
                slotSnapshot=ready
                slotCount=128
                targetCount=93
                engine=installed
                template=trusted
                alignment=compatibility
                mode=compatibility
                reason=
                cachePending=no
            """.trimIndent(),
        )

        assertEquals("ready", state.slotSnapshot)
        assertEquals(128, state.slotCount)
        assertEquals(93, state.targetCount)
    }

    @Test
    fun emptyBridgeOutputReturnsReadableError() {
        val state = parseDeviceTrustOutput("")

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
        assertTrue(state.error.isNotBlank())
    }
}
