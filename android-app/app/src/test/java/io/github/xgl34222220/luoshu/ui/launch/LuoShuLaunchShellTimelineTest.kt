package io.github.xgl34222220.luoshu.ui.launch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LuoShuLaunchShellTimelineTest {
    @Test fun firstFrameMatchesTheStaticHandOff() {
        val first = LuoShuLaunchShellTimeline.first(textVisible = true)
        assertEquals(0f, first.drift, 0f)
        assertEquals(0f, first.accent, 0f)
        assertEquals(LuoShuLaunchArtwork.CARD_START_SCALE, first.cardScale, 1e-6f)
        assertEquals(-1f, first.shimmer, 0f)
        assertEquals(1f, first.textAlpha, 0f)
        assertEquals(0f, first.textRiseDp, 0f)
        assertEquals(1f, LuoShuLaunchShellTimeline.shellAlpha(0f), 0f)
        // API 28-30: the starting window has no text; it fades in from the first Compose frame.
        assertEquals(0f, LuoShuLaunchShellTimeline.first(textVisible = false).textAlpha, 0f)
    }

    @Test fun shellIsOpaqueUntilTheExitThenFullyGone() {
        for (ms in listOf(0f, 200f, 600f, LuoShuLaunchShellTimeline.EXIT_START_MS)) assertEquals(1f, LuoShuLaunchShellTimeline.shellAlpha(ms), 1e-6f)
        assertTrue(LuoShuLaunchShellTimeline.shellAlpha(LuoShuLaunchShellTimeline.EXIT_START_MS + LuoShuLaunchShellTimeline.EXIT_MS / 2) in .05f..0.95f)
        assertEquals(0f, LuoShuLaunchShellTimeline.shellAlpha(LuoShuLaunchShellTimeline.TOTAL_MS), 1e-6f)
        assertTrue(LuoShuLaunchShellTimeline.TOTAL_MS <= 1500f)
    }

    @Test fun shimmerIsOneShotAndFinishedBeforeTheCrossfade() {
        assertTrue(LuoShuLaunchShellTimeline.SHIMMER_END_MS < LuoShuLaunchShellTimeline.EXIT_START_MS)
        assertEquals(-1f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.SHIMMER_START_MS - 1f, true).shimmer, 0f)
        assertEquals(0f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.SHIMMER_START_MS, true).shimmer, 1e-6f)
        assertEquals(1f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.SHIMMER_END_MS, true).shimmer, 1e-6f)
        assertEquals(-1f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.SHIMMER_END_MS + 1f, true).shimmer, 0f)
    }

    @Test fun cardSettlesMonotonicallyAndDriftIsBounded() {
        var previous = 0f
        for (ms in 0..LuoShuLaunchShellTimeline.CARD_SETTLE_MS.toInt() step 20) {
            val scale = LuoShuLaunchShellTimeline.frameAt(ms.toFloat(), true).cardScale
            assertTrue(scale >= previous)
            previous = scale
        }
        assertEquals(1f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.CARD_SETTLE_MS, true).cardScale, 1e-4f)
        assertEquals(1.025f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.TOTAL_MS, true).cardScale, 1e-4f)
        assertEquals(1f, LuoShuLaunchShellTimeline.frameAt(10_000f, true).drift, 0f)
        assertEquals(1f, LuoShuLaunchShellTimeline.frameAt(LuoShuLaunchShellTimeline.TEXT_FADE_MS, false).textAlpha, 1e-6f)
    }
}
