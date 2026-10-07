package io.github.xgl34222220.luoshu.ui.launch

import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchExitPolicy.Action
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LuoShuLaunchExitPolicyTest {
    @Test fun lateNativeExitCannotFadeArtworkBehindTheSystemLayer() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        assertEquals(Action.NONE, policy.onContentDrawn())
        repeat(20) { assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true)) }
        assertEquals(Action.SCHEDULE_FADE, policy.onNativeRemoved())
        assertEquals(Action.START_FADE, policy.onNextFrame(animatorsEnabled = true))
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun nativeRemovedBeforeContentDrawStillWaitsForContent() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        assertEquals(Action.NONE, policy.onNativeRemoved())
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
        assertEquals(Action.SCHEDULE_FADE, policy.onContentDrawn())
        assertEquals(Action.START_FADE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun receivedCallbackCancelsWatchdogButDoesNotStartFadeUntilRemoval() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertTrue(policy.awaitsNativeCallback)
        policy.onNativeExitReceived()
        assertEquals(false, policy.awaitsNativeCallback)
        assertEquals(Action.NONE, policy.onMissingNativeExit())
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
        assertEquals(Action.SCHEDULE_FADE, policy.onNativeRemoved())
        assertEquals(Action.START_FADE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun legacyPlatformDoesNotWaitForANativeCallback() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = false)
        assertEquals(Action.SCHEDULE_FADE, policy.onContentDrawn())
        assertEquals(Action.START_FADE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun stopWhileWaitingMakesALateCallbackInert() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertEquals(Action.FINISH, policy.finish())
        assertEquals(Action.NONE, policy.onNativeRemoved())
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertTrue(policy.isComplete)
    }

    @Test fun stopBetweenSchedulingAndTheNextFramePreventsFade() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        policy.onContentDrawn()
        assertEquals(Action.SCHEDULE_FADE, policy.onNativeRemoved())
        assertEquals(Action.FINISH, policy.finish())
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun missingNativeCallbackFinishesAndALateRemovalNeverRestartsArtwork() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        policy.onContentDrawn()
        assertEquals(Action.FINISH, policy.onMissingNativeExit())
        assertEquals(Action.NONE, policy.onNativeRemoved())
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
        assertEquals(Action.NONE, policy.onMissingNativeExit())
    }

    @Test fun watchdogDoesNotFinishBeforeContentOrAfterNativeRemoval() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        assertEquals(Action.NONE, policy.onMissingNativeExit())
        policy.onNativeRemoved()
        assertEquals(Action.NONE, policy.onMissingNativeExit())
        assertEquals(Action.SCHEDULE_FADE, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.onMissingNativeExit())
        assertEquals(Action.START_FADE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun reducedMotionAtInstallCompletesWithoutContentOrNativeEvents() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        assertEquals(Action.FINISH, policy.onInstall(artworkEnabled = false))
        assertTrue(policy.isComplete)
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertEquals(Action.NONE, policy.onNativeRemoved())
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = false))
    }

    @Test fun animationDisabledAfterSchedulingFinishesInsteadOfStartingFade() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        policy.onContentDrawn()
        policy.onNativeRemoved()
        assertEquals(Action.FINISH, policy.onNextFrame(animatorsEnabled = false))
        assertTrue(policy.isComplete)
        assertEquals(Action.NONE, policy.onNextFrame(animatorsEnabled = true))
    }

    @Test fun repeatedReadyEventsScheduleOnlyOneExit() {
        val policy = LuoShuLaunchExitPolicy(nativeExitRequired = true)
        policy.onContentDrawn()
        assertEquals(Action.SCHEDULE_FADE, policy.onNativeRemoved())
        assertEquals(Action.NONE, policy.onNativeRemoved())
        assertEquals(Action.NONE, policy.onContentDrawn())
        assertEquals(Action.START_FADE, policy.onNextFrame(animatorsEnabled = true))
        assertEquals(Action.NONE, policy.onMissingNativeExit())
        assertEquals(Action.FINISH, policy.finish())
        assertEquals(Action.NONE, policy.finish())
    }
}
