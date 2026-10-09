package io.github.xgl34222220.luoshu

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class QuickReturnDockPolicyTest {
    private fun policy() = QuickReturnDockPolicy(hideThresholdPx = 34f, showThresholdPx = 6f)

    @Test fun deliberateDownwardContentTravelHidesOnlyAtThreshold() {
        val policy = policy()
        assertFalse(policy.onScroll(-20f, userInput = true))
        assertFalse(policy.onScroll(-13f, userInput = true))
        assertTrue(policy.onScroll(-1f, userInput = true))
    }

    @Test fun shortReverseDragRestoresNavigationWithoutRequiringTwentyPixels() {
        val policy = policy()
        assertTrue(policy.onScroll(-34f, userInput = true))
        assertTrue(policy.onScroll(5f, userInput = true))
        assertFalse(policy.onScroll(1f, userInput = true))
    }

    @Test fun subpixelInputCountsAtHighRefreshRates() {
        val policy = policy()
        repeat(67) { assertFalse(policy.onScroll(-.5f, userInput = true)) }
        assertTrue(policy.onScroll(-.5f, userInput = true))
        repeat(11) { assertTrue(policy.onScroll(.5f, userInput = true)) }
        assertFalse(policy.onScroll(.5f, userInput = true))
    }

    @Test fun residualFlingAndPaddingAnimationCannotRehideARecoveredDock() {
        val policy = policy()
        policy.onScroll(-34f, userInput = true)
        assertFalse(policy.onScroll(6f, userInput = true))
        repeat(30) { assertFalse(policy.onScroll(-108f, userInput = false)) }
        assertFalse(policy.hidden)
    }

    @Test fun programmaticScrollCannotHideOrReveal() {
        val policy = policy()
        assertFalse(policy.onScroll(-1000f, userInput = false))
        assertTrue(policy.onScroll(-34f, userInput = true))
        assertTrue(policy.onScroll(1000f, userInput = false))
    }

    @Test fun sideEffectsDoNotAddToOrClearTheCurrentUserIntent() {
        val policy = policy()
        assertFalse(policy.onScroll(-20f, userInput = true))
        assertFalse(policy.onScroll(-1000f, userInput = false))
        assertFalse(policy.onScroll(1000f, userInput = false))
        assertTrue(policy.onScroll(-14f, userInput = true))
        assertTrue(policy.onScroll(3f, userInput = true))
        assertTrue(policy.onScroll(-1000f, userInput = false))
        assertFalse(policy.onScroll(3f, userInput = true))
    }

    @Test fun reversingBeforeHideClearsTheIncompleteHideIntent() {
        val policy = policy()
        policy.onScroll(-30f, userInput = true)
        assertFalse(policy.onScroll(2f, userInput = true))
        assertFalse(policy.onScroll(-30f, userInput = true))
        assertTrue(policy.onScroll(-4f, userInput = true))
    }

    @Test fun reversingBeforeRevealClearsTheIncompleteRevealIntent() {
        val policy = policy()
        policy.onScroll(-34f, userInput = true)
        assertTrue(policy.onScroll(5f, userInput = true))
        assertTrue(policy.onScroll(-2f, userInput = true))
        assertTrue(policy.onScroll(5f, userInput = true))
        assertFalse(policy.onScroll(1f, userInput = true))
    }

    @Test fun continuedDownwardDragDoesNotCreateAReverseScrollDebt() {
        val policy = policy()
        assertTrue(policy.onScroll(-400f, userInput = true))
        assertTrue(policy.onScroll(-400f, userInput = true))
        assertFalse(policy.onScroll(6f, userInput = true))
    }

    @Test fun gestureEndClearsIncompleteIntentWithoutChangingVisibility() {
        val policy = policy()
        policy.onScroll(-30f, userInput = true)
        policy.finishGesture()
        assertFalse(policy.onScroll(-4f, userInput = true))
        assertTrue(policy.onScroll(-30f, userInput = true))
        policy.onScroll(5f, userInput = true)
        policy.finishGesture()
        assertTrue(policy.hidden)
        assertTrue(policy.onScroll(1f, userInput = true))
        assertFalse(policy.onScroll(5f, userInput = true))
    }

    @Test fun returnToAppOrDetailParentResetsVisibilityAndIncompleteIntent() {
        val policy = policy()
        policy.onScroll(-34f, userInput = true)
        policy.onScroll(5f, userInput = true)
        policy.reset()
        assertFalse(policy.hidden)
        assertFalse(policy.onScroll(-33f, userInput = true))
        policy.reset()
        assertFalse(policy.onScroll(-1f, userInput = true))
        assertFalse(policy.onScroll(-1000f, userInput = false))
    }

    @Test fun repeatedHideAndRevealCyclesRemainIndependent() {
        val policy = policy()
        repeat(100) {
            assertTrue(policy.onScroll(-34f, userInput = true))
            policy.finishGesture()
            assertTrue(policy.onScroll(-1000f, userInput = false))
            assertFalse(policy.onScroll(6f, userInput = true))
            policy.finishGesture()
            assertFalse(policy.onScroll(-1000f, userInput = false))
        }
    }

    @Test fun invalidAndZeroDeltasCannotPoisonIntent() {
        val policy = policy()
        listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY, 0f).forEach {
            assertFalse(policy.onScroll(it, userInput = true))
        }
        assertTrue(policy.onScroll(-34f, userInput = true))
        listOf(Float.NaN, Float.POSITIVE_INFINITY, Float.NEGATIVE_INFINITY, 0f).forEach {
            assertTrue(policy.onScroll(it, userInput = true))
        }
        assertFalse(policy.onScroll(6f, userInput = true))
    }

    @Test fun backdropCaptureStopsOnlyWhenTheHiddenTransitionIsIdle() {
        assertTrue(dockBackdropCaptureRequired(currentVisible = true, targetVisible = true, transitionIdle = true))
        assertTrue(dockBackdropCaptureRequired(currentVisible = false, targetVisible = true, transitionIdle = false))
        assertTrue(dockBackdropCaptureRequired(currentVisible = true, targetVisible = false, transitionIdle = false))
        assertFalse(dockBackdropCaptureRequired(currentVisible = false, targetVisible = false, transitionIdle = true))
    }

    @Test fun interruptedEntryStillCapturesThroughItsExitAnimation() {
        // The dock can begin entering from false and reverse before currentState ever becomes true.
        assertTrue(dockBackdropCaptureRequired(currentVisible = false, targetVisible = false, transitionIdle = false))
        assertFalse(dockBackdropCaptureRequired(currentVisible = false, targetVisible = false, transitionIdle = true))
    }

    @Test(expected = IllegalArgumentException::class)
    fun nonpositiveHideThresholdIsRejected() {
        QuickReturnDockPolicy(hideThresholdPx = 0f, showThresholdPx = 6f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun nonfiniteShowThresholdIsRejected() {
        QuickReturnDockPolicy(hideThresholdPx = 34f, showThresholdPx = Float.NaN)
    }
}
