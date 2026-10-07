package io.github.xgl34222220.luoshu

/** Scroll intent only. Fling and layout/bring-into-view scrolls must not change the dock. */
internal class QuickReturnDockPolicy(
    private val hideThresholdPx: Float,
    private val showThresholdPx: Float,
) {
    init {
        require(hideThresholdPx.isFinite() && hideThresholdPx > 0f)
        require(showThresholdPx.isFinite() && showThresholdPx > 0f)
    }

    var hidden: Boolean = false
        private set
    private var accumulatedPx = 0f

    fun onScroll(deltaY: Float, userInput: Boolean): Boolean {
        if (!userInput || !deltaY.isFinite() || deltaY == 0f) return hidden

        if (hidden) {
            if (deltaY > 0f) {
                accumulatedPx += deltaY
                if (accumulatedPx >= showThresholdPx) reset()
            } else {
                accumulatedPx = 0f
            }
        } else {
            if (deltaY < 0f) {
                accumulatedPx -= deltaY
                if (accumulatedPx >= hideThresholdPx) {
                    hidden = true
                    accumulatedPx = 0f
                }
            } else {
                accumulatedPx = 0f
            }
        }
        return hidden
    }

    /** Discard incomplete intent when a drag ends without letting its fling hide the dock. */
    fun finishGesture() {
        accumulatedPx = 0f
    }

    /** Returning to the app or a main destination always restores its navigation. */
    fun reset() {
        hidden = false
        accumulatedPx = 0f
    }
}

/** Keep sampling through both enter and exit; stop only once the dock is fully absent. */
internal fun dockBackdropCaptureRequired(
    currentVisible: Boolean,
    targetVisible: Boolean,
    transitionIdle: Boolean,
): Boolean = currentVisible || targetVisible || !transitionIdle
