package io.github.xgl34222220.luoshu.ui.launch

import org.junit.Assert.*
import org.junit.Test

class LuoShuNativeShellPolicyTest {
    @Test fun onlyNewApi31HomeActivitiesAreEligible() {
        for (api in listOf(28, 29, 30, 31, 36)) {
            for (restored in listOf(false, true)) for (task in listOf(false, true)) {
                assertEquals(api >= 31 && !restored && !task,
                    LuoShuNativeShellPolicy.eligible(api, restored, task))
            }
        }
    }

    @Test fun submissionCannotBeSkippedOrRepeated() {
        val policy = LuoShuNativeShellPolicy()
        assertFalse(policy.beginContent())
        assertTrue(policy.onShellSubmitted())
        assertEquals(LuoShuNativeShellPolicy.Phase.SHELL_SUBMITTED, policy.phase)
        assertFalse(policy.onShellSubmitted())
        assertTrue(policy.beginContent())
        repeat(20) {
            assertFalse(policy.onShellSubmitted())
            assertFalse(policy.beginContent())
            assertFalse(policy.beginContent(softwareFallback = true))
        }
        assertEquals(LuoShuNativeShellPolicy.Phase.CONTENT, policy.phase)
    }

    @Test fun softwareBypassesShellSubmissionWithoutFakingACommit() {
        val policy = LuoShuNativeShellPolicy()
        assertTrue(policy.beginContent(softwareFallback = true))
        assertFalse(policy.onShellSubmitted())
        assertEquals(LuoShuNativeShellPolicy.Phase.CONTENT, policy.phase)
    }

    @Test fun destructionInvalidatesEveryLateCallbackAndCannotAffectRecreation() {
        for (step in 0..2) {
            val old = LuoShuNativeShellPolicy()
            if (step > 0) old.onShellSubmitted()
            if (step > 1) old.beginContent()
            old.dispose()
            assertFalse(old.onShellSubmitted())
            assertFalse(old.beginContent())
            assertFalse(old.beginContent(softwareFallback = true))
            assertEquals(LuoShuNativeShellPolicy.Phase.DISPOSED, old.phase)
            val fresh = LuoShuNativeShellPolicy()
            assertTrue(fresh.onShellSubmitted())
            assertTrue(fresh.beginContent())
            assertEquals(LuoShuNativeShellPolicy.Phase.DISPOSED, old.phase)
        }
    }

    @Test fun shellSubmissionNeverReleasesRealContentPolicy() {
        val shell = LuoShuNativeShellPolicy()
        val content = LuoShuFirstFramePolicy()
        shell.onShellSubmitted()
        assertFalse(content.isReady)
        shell.beginContent()
        assertFalse(content.isReady)
        assertEquals(LuoShuFirstFramePolicy.DrawAction.WAIT_FOR_COMMIT, content.onDraw(true, true))
        assertTrue(content.onFrameDelivered())
        assertTrue(content.isReady)
    }
}
