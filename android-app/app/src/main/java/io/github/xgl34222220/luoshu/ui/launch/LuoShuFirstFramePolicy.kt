package io.github.xgl34222220.luoshu.ui.launch

/** Delivery ordering for the first real page; this never controls the native splash. */
internal class LuoShuFirstFramePolicy {
    enum class DrawAction { NONE, WAIT_FOR_COMMIT, POST_DRAW_DELIVERY }

    private var drawObserved = false
    private var disposed = false
    var isReady = false
        private set

    fun onDraw(frameCommitSupported: Boolean, hardwareAccelerated: Boolean): DrawAction {
        if (disposed || drawObserved || isReady) return DrawAction.NONE
        drawObserved = true
        return if (frameCommitSupported && hardwareAccelerated) {
            DrawAction.WAIT_FOR_COMMIT
        } else {
            DrawAction.POST_DRAW_DELIVERY
        }
    }

    fun onFrameDelivered(): Boolean {
        if (disposed || isReady) return false
        isReady = true
        return true
    }

    fun dispose() {
        disposed = true
    }
}
