package io.github.xgl34222220.luoshu.ui.home

import io.github.xgl34222220.luoshu.ui.settings.HealthLevel
import io.github.xgl34222220.luoshu.ui.settings.parseHealthReport
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** #199: a device-font cache marker must map to a terminal failed state with recovery actions. */
class DeviceCacheStateTest {
    private fun trust(cacheLines: String, alignment: String = "pending") = parseDeviceTrustOutput(
        """
            activeFont=custom-font
            inventory=available
            engine=missing
            template=trusted
            alignment=$alignment
            mode=compatibility
            reason=
            mountState=idle
            $cacheLines
        """.trimIndent(),
    )

    @Test
    fun timedOutCacheIsFailedWithRecoveryActions() {
        val state = trust("cachePending=no\ncacheState=failed:timeout")

        assertFalse(state.cachePending)
        assertEquals("timeout", state.cacheFailure)
        assertEquals(DeviceCacheStatus.FAILED, deviceCacheStatus(state))
        assertEquals(DeviceTrustLevel.ISSUE, state.level)
        assertTrue(deviceCacheRecoveryAvailable(state))
        assertEquals("等待超时，生成任务没有完成", deviceCacheRowText(state))
    }

    @Test
    fun failedStateWinsEvenIfOldReaderStillSaysPending() {
        val state = trust("cachePending=yes\ncacheState=failed:build-retry-exhausted")

        assertFalse(state.cachePending)
        assertEquals("build-retry-exhausted", state.cacheFailure)
        assertEquals("连续多次生成失败，已停止重试", deviceCacheRowText(state))
    }

    @Test
    fun pendingCacheStaysPendingWithoutRecoveryActions() {
        val state = trust("cachePending=yes\ncacheState=pending")

        assertTrue(state.cachePending)
        assertEquals("", state.cacheFailure)
        assertEquals(DeviceCacheStatus.PENDING, deviceCacheStatus(state))
        assertEquals(DeviceTrustLevel.PENDING, state.level)
        assertFalse(deviceCacheRecoveryAvailable(state))
        assertEquals("等待生成", deviceCacheRowText(state))
    }

    @Test
    fun legacyOutputWithoutCacheStateKeepsOldMeaning() {
        val pending = trust("cachePending=yes")
        assertTrue(pending.cachePending)
        assertEquals(DeviceCacheStatus.PENDING, deviceCacheStatus(pending))

        val none = trust("cachePending=no")
        assertEquals(DeviceCacheStatus.NONE, deviceCacheStatus(none))
        assertEquals("无待处理任务", deviceCacheRowText(none))
    }

    @Test
    fun verifiedFontIsNotDowngradedByAStaleCacheFailure() {
        val state = parseDeviceTrustOutput(
            """
                activeFont=custom-font
                inventory=available
                engine=installed
                template=trusted
                alignment=verified
                mode=aligned
                cachePending=no
                cacheState=failed:timeout
            """.trimIndent(),
        )

        assertEquals(DeviceTrustLevel.VERIFIED, state.level)
        assertTrue(deviceCacheRecoveryAvailable(state))
    }

    @Test
    fun loadingStateNeverOffersActions() {
        val state = DeviceTrustState(loading = true, cacheFailure = "timeout")
        assertFalse(deviceCacheRecoveryAvailable(state))
    }

    @Test
    fun failureReasonParsing() {
        assertEquals("", cacheFailureReason(null))
        assertEquals("", cacheFailureReason("pending"))
        assertEquals("", cacheFailureReason("none"))
        assertEquals("timeout", cacheFailureReason("failed:timeout"))
        assertEquals("unknown", cacheFailureReason("failed"))
        assertEquals("unknown", cacheFailureReason("failed:"))
        assertEquals("生成失败（odd）", friendlyCacheFailure("odd"))
    }

    @Test
    fun healthReportSurfacesCacheFailureInsteadOfEndlessWaiting() {
        val state = parseHealthReport(
            """
                healthVersion=1
                modulePresent=true
                activeFont=default
                payloadFonts=0
                lockState=idle
                alignmentState=verified
                cachePending=true
                cacheState=failed:timeout
                recentErrors=0
            """.trimIndent(),
        )
        assertFalse(state.cachePending)
        assertEquals("timeout", state.cacheFailure)
        assertEquals(HealthLevel.WARNING, state.level)
    }
}
