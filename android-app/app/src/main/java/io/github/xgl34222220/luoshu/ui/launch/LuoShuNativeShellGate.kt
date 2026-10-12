package io.github.xgl34222220.luoshu.ui.launch

/**
 * Holds the API 31+ preparation traversal until its pixels already exist.
 *
 * The platform keeps its splash while the Activity has not drawn. Once the first draw is
 * issued, WindowManager waits at most ~1s for that buffer and then starts the default splash
 * exit anyway. A slow first render (glass blur, shader setup on a loaded device) therefore
 * revealed an empty, black Window. The shell is rasterised off the main thread first, so the
 * first submitted frame only draws one finished bitmap. Pure state, unit tested on the JVM.
 */
internal class LuoShuNativeShellGate(private val holdLimitMs: Long = HOLD_LIMIT_MS) {
    enum class State { IDLE, RENDERING, READY, EXPIRED, DISPOSED }
    enum class Decision { START_RENDER, HOLD, DRAW }

    var state = State.IDLE
        private set
    private var firstPreDrawAt = -1L

    /** Called from each preparation pre-draw; START_RENDER and HOLD cancel that traversal. */
    fun onPreDraw(nowMs: Long, sizeKnown: Boolean): Decision {
        if (firstPreDrawAt < 0) firstPreDrawAt = nowMs
        return when (state) {
            State.READY, State.EXPIRED, State.DISPOSED -> Decision.DRAW
            State.IDLE, State.RENDERING -> when {
                // Bounded: a stuck or failed rasteriser falls back to the live drawing.
                nowMs - firstPreDrawAt >= holdLimitMs -> {
                    state = State.EXPIRED
                    Decision.DRAW
                }
                state == State.IDLE && sizeKnown -> {
                    state = State.RENDERING
                    Decision.START_RENDER
                }
                else -> Decision.HOLD
            }
        }
    }

    /** A finished bitmap is used only while still awaited; late results never swap pixels. */
    fun onRendered(): Boolean {
        if (state != State.RENDERING) return false
        state = State.READY
        return true
    }

    fun onFailed() {
        if (state == State.IDLE || state == State.RENDERING) state = State.EXPIRED
    }

    fun dispose() { state = State.DISPOSED }

    companion object {
        const val HOLD_LIMIT_MS = 4000L
    }
}
