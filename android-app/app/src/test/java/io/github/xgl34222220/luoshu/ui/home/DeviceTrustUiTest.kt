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
    fun emptyBridgeOutputReturnsReadableError() {
        val state = parseDeviceTrustOutput("")

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
        assertTrue(state.error.isNotBlank())
    }
}
