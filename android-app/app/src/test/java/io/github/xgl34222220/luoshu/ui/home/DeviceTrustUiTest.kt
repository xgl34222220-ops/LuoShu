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
                inventory=available
                engine=installed
                template=trusted
                alignment=verified
                mode=aligned
                cachePending=no
            """.trimIndent(),
        )

        assertFalse(state.loading)
        assertEquals(DeviceTrustLevel.VERIFIED, state.level)
        assertEquals("trusted", state.template)
        assertFalse(state.cachePending)
    }

    @Test
    fun failedAlignmentTakesPriority() {
        val state = parseDeviceTrustOutput(
            """
                inventory=available
                engine=installed
                template=trusted
                alignment=failed
                mode=compatibility
                cachePending=yes
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
        assertTrue(state.cachePending)
    }

    @Test
    fun emptyBridgeOutputReturnsReadableError() {
        val state = parseDeviceTrustOutput("")

        assertEquals(DeviceTrustLevel.ISSUE, state.level)
        assertTrue(state.error.isNotBlank())
    }
}
