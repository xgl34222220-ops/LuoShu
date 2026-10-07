package io.github.xgl34222220.luoshu.ui.launch

import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchExitPolicy.Action
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LuoShuLaunchExitPolicyTest {
    @Test fun nativeCallbackAlwaysRequestsImmediateRemoval() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.REMOVE_NATIVE, policy.onNativeExit())
        assertFalse(policy.isComplete)
    }

    @Test fun contentCompletesWithoutWaitingForAnOemNativeCallback() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertTrue(policy.isComplete)
    }

    @Test fun nativeCallbackBeforeContentCannotManufactureAContentFrame() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.REMOVE_NATIVE, policy.onNativeExit())
        assertFalse(policy.isComplete)
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertTrue(policy.isComplete)
    }

    @Test fun callbackAfterContentStillRemovesItsSystemView() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertEquals(Action.REMOVE_NATIVE, policy.onNativeExit())
        assertEquals(Action.NONE, policy.onContentDrawn())
    }

    @Test fun interruptionBeforeContentCompletesOnlyOnceAndStillCleansLateNativeViews() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.finish())
        repeat(20) {
            assertEquals(Action.NONE, policy.finish())
            assertEquals(Action.NONE, policy.onContentDrawn())
            assertEquals(Action.REMOVE_NATIVE, policy.onNativeExit())
        }
        assertTrue(policy.isComplete)
    }

    @Test fun repeatedNativeCallbacksNeverScheduleOrRestartABrandPage() {
        val policy = LuoShuLaunchExitPolicy()
        repeat(20) { assertEquals(Action.REMOVE_NATIVE, policy.onNativeExit()) }
        assertEquals(Action.FINISH, policy.onContentDrawn())
        repeat(20) { assertEquals(Action.REMOVE_NATIVE, policy.onNativeExit()) }
        assertEquals(Action.NONE, policy.finish())
    }

    @Test fun legacyLaunchNeedsOnlyTheActualContentFrame() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.finish())
    }

    @Test fun allEventOrderingsKeepOneShotCompletionAndUnconditionalNativeCleanup() {
        // Covers callbacks arriving before/after a draw, stop, task entry, or destroy.
        // Reduced motion follows these same events: there is no animation-dependent path.
        repeat(81) { encoded ->
            val policy = LuoShuLaunchExitPolicy()
            var digits = encoded
            var completionSeen = false
            repeat(4) {
                val event = digits % 3
                digits /= 3
                val action = when (event) {
                    0 -> policy.onNativeExit()
                    1 -> policy.onContentDrawn()
                    else -> policy.finish()
                }
                val expected = if (event == 0) Action.REMOVE_NATIVE else
                    if (completionSeen) Action.NONE else Action.FINISH
                assertEquals("sequence=$encoded event=$event", expected, action)
                if (event != 0) completionSeen = true
                assertEquals(completionSeen, policy.isComplete)
            }
        }
    }
}
