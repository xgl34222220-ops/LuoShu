package io.github.xgl34222220.luoshu.ui.launch

import io.github.xgl34222220.luoshu.ui.launch.LuoShuNativeShellGate.Decision
import io.github.xgl34222220.luoshu.ui.launch.LuoShuNativeShellGate.State
import org.junit.Assert.*
import org.junit.Test

class LuoShuNativeShellGateTest {
    @Test fun firstSizedTraversalStartsOneRasterAndHoldsUntilItIsReady() {
        val gate = LuoShuNativeShellGate(holdLimitMs = 2500)
        assertEquals(Decision.HOLD, gate.onPreDraw(0, sizeKnown = false))
        assertEquals(Decision.START_RENDER, gate.onPreDraw(16, sizeKnown = true))
        repeat(50) { assertEquals(Decision.HOLD, gate.onPreDraw(32L + it * 16, sizeKnown = true)) }
        assertEquals(State.RENDERING, gate.state)
        assertTrue(gate.onRendered())
        assertEquals(Decision.DRAW, gate.onPreDraw(900, sizeKnown = true))
        assertFalse(gate.onRendered())
        assertEquals(State.READY, gate.state)
    }

    @Test fun holdIsBoundedFromTheFirstTraversalAndLateRasterIsDropped() {
        val gate = LuoShuNativeShellGate(holdLimitMs = 2500)
        assertEquals(Decision.HOLD, gate.onPreDraw(1000, sizeKnown = false))
        assertEquals(Decision.START_RENDER, gate.onPreDraw(1400, sizeKnown = true))
        assertEquals(Decision.HOLD, gate.onPreDraw(3499, sizeKnown = true))
        assertEquals(Decision.DRAW, gate.onPreDraw(3500, sizeKnown = true))
        assertEquals(State.EXPIRED, gate.state)
        // A bitmap finishing after the live fallback was drawn must not swap pixels.
        assertFalse(gate.onRendered())
        assertEquals(Decision.DRAW, gate.onPreDraw(3600, sizeKnown = true))
    }

    @Test fun neverSizedWindowStillDrawsAfterTheLimit() {
        val gate = LuoShuNativeShellGate(holdLimitMs = 100)
        assertEquals(Decision.HOLD, gate.onPreDraw(0, sizeKnown = false))
        assertEquals(Decision.HOLD, gate.onPreDraw(99, sizeKnown = false))
        assertEquals(Decision.DRAW, gate.onPreDraw(100, sizeKnown = false))
        assertFalse(gate.onRendered())
    }

    @Test fun rasterFailureFallsBackToLiveDrawingImmediately() {
        val gate = LuoShuNativeShellGate()
        assertEquals(Decision.START_RENDER, gate.onPreDraw(0, sizeKnown = true))
        gate.onFailed()
        assertEquals(State.EXPIRED, gate.state)
        assertEquals(Decision.DRAW, gate.onPreDraw(16, sizeKnown = true))
        assertFalse(gate.onRendered())
    }

    @Test fun disposalInvalidatesLateCallbacks() {
        val gate = LuoShuNativeShellGate()
        assertEquals(Decision.START_RENDER, gate.onPreDraw(0, sizeKnown = true))
        gate.dispose()
        assertFalse(gate.onRendered())
        gate.onFailed()
        assertEquals(State.DISPOSED, gate.state)
        assertEquals(Decision.DRAW, gate.onPreDraw(16, sizeKnown = true))
    }

    @Test fun defaultLimitKeepsTheSplashBoundedButAboveTheWindowDrawTimeout() {
        // WindowManager gives a submitted first draw ~1s; the hold happens before any draw.
        assertTrue(LuoShuNativeShellGate.HOLD_LIMIT_MS in 1000L..3000L)
    }
}
