package io.github.xgl34222220.luoshu.ui.launch

import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchExitPolicy.Action
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LuoShuLaunchExitPolicyTest {
    @Test fun launchDoesNotCompleteBeforeContentOrAnInterruption() {
        val policy = LuoShuLaunchExitPolicy()
        assertFalse(policy.isComplete)
    }

    @Test fun contentCompletesWithoutWaitingForAnOemNativeCallback() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertTrue(policy.isComplete)
    }

    @Test fun interruptionAfterContentCannotRepeatCompletion() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.finish())
        assertEquals(Action.NONE, policy.onContentDrawn())
    }

    @Test fun interruptionBeforeContentCompletesOnlyOnce() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.finish())
        repeat(20) {
            assertEquals(Action.NONE, policy.finish())
            assertEquals(Action.NONE, policy.onContentDrawn())
        }
        assertTrue(policy.isComplete)
    }

    @Test fun legacyLaunchNeedsOnlyTheActualContentFrame() {
        val policy = LuoShuLaunchExitPolicy()
        assertEquals(Action.FINISH, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.finish())
    }

    @Test fun allContentAndInterruptionOrderingsCompleteOnlyOnce() {
        // A draw, stop, task entry and destroy can arrive in either order. Native
        // exit is a platform concern and is deliberately absent from this policy.
        repeat(16) { encoded ->
            val policy = LuoShuLaunchExitPolicy()
            var digits = encoded
            var completionSeen = false
            repeat(4) {
                val event = digits % 2
                digits /= 2
                val action = if (event == 0) policy.onContentDrawn() else policy.finish()
                val expected = if (completionSeen) Action.NONE else Action.FINISH
                assertEquals("sequence=$encoded event=$event", expected, action)
                completionSeen = true
                assertEquals(completionSeen, policy.isComplete)
            }
        }
    }
}
