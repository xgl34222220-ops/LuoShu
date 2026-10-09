package io.github.xgl34222220.luoshu.ui.launch

import io.github.xgl34222220.luoshu.ui.launch.LuoShuFirstFramePolicy.DrawAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LuoShuFirstFramePolicyTest {
    @Test fun hardwareDrawWaitsForTheFrameToBeSubmitted() {
        val policy = LuoShuFirstFramePolicy()
        assertEquals(DrawAction.WAIT_FOR_COMMIT, policy.onDraw(true, true))
        assertFalse(policy.isReady)
        assertEquals(DrawAction.NONE, policy.onDraw(true, true))
        assertFalse(policy.isReady)
        assertTrue(policy.onFrameDelivered())
        assertTrue(policy.isReady)
    }

    @Test fun legacyAndSoftwareDrawingUsePostDrawDelivery() {
        for ((commitSupported, hardwareAccelerated) in listOf(false to true, true to false, false to false)) {
            val policy = LuoShuFirstFramePolicy()
            assertEquals(DrawAction.POST_DRAW_DELIVERY, policy.onDraw(commitSupported, hardwareAccelerated))
            assertFalse(policy.isReady)
            assertTrue(policy.onFrameDelivered())
            assertTrue(policy.isReady)
        }
    }

    @Test fun pendingCommitAndPostDrawCallbacksCannotReleaseAfterDestroy() {
        for ((commitSupported, hardwareAccelerated) in listOf(true to true, false to true, true to false)) {
            val policy = LuoShuFirstFramePolicy()
            policy.onDraw(commitSupported, hardwareAccelerated)
            policy.dispose()
            assertFalse(policy.onFrameDelivered())
            assertFalse(policy.isReady)
            assertEquals(DrawAction.NONE, policy.onDraw(commitSupported, hardwareAccelerated))
        }
    }

    @Test fun destroyBeforeDrawingCannotScheduleOrDeliverAFrame() {
        val policy = LuoShuFirstFramePolicy()
        policy.dispose()
        assertEquals(DrawAction.NONE, policy.onDraw(true, true))
        assertEquals(DrawAction.NONE, policy.onDraw(false, false))
        assertFalse(policy.onFrameDelivered())
        assertFalse(policy.isReady)
    }

    @Test fun duplicateDeliveryCannotRepeatTheRelease() {
        val policy = LuoShuFirstFramePolicy()
        policy.onDraw(true, true)
        assertTrue(policy.onFrameDelivered())
        repeat(20) {
            assertFalse(policy.onFrameDelivered())
            assertEquals(DrawAction.NONE, policy.onDraw(true, true))
        }
        policy.dispose()
        assertFalse(policy.onFrameDelivered())
        assertTrue(policy.isReady)
    }

    @Test fun recreationStartsWithAnIndependentFirstFrame() {
        val oldActivity = LuoShuFirstFramePolicy()
        oldActivity.onDraw(true, true)
        oldActivity.dispose()
        val newActivity = LuoShuFirstFramePolicy()
        assertFalse(newActivity.isReady)
        assertFalse(oldActivity.onFrameDelivered())
        assertEquals(DrawAction.WAIT_FOR_COMMIT, newActivity.onDraw(true, true))
        assertTrue(newActivity.onFrameDelivered())
        assertFalse(oldActivity.isReady)
    }
}
