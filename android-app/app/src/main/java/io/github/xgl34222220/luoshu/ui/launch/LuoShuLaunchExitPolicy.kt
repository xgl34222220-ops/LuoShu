package io.github.xgl34222220.luoshu.ui.launch

/** Event ordering only; Android owns drawing, animation and lifecycle cleanup. */
internal class LuoShuLaunchExitPolicy(nativeExitRequired: Boolean) {
    enum class Action { NONE, SCHEDULE_FADE, START_FADE, FINISH }

    var isComplete: Boolean = false
        private set

    private var contentDrawn = false
    private var nativeExitReceived = !nativeExitRequired
    private var nativeRemoved = !nativeExitRequired
    private var fadeScheduled = false
    private var fadeStarted = false
    val awaitsNativeCallback: Boolean get() = contentDrawn && !nativeExitReceived && !isComplete

    fun onInstall(artworkEnabled: Boolean): Action = if (artworkEnabled) Action.NONE else finish()

    fun onContentDrawn(): Action {
        contentDrawn = true
        return scheduleWhenReady()
    }

    fun onNativeExitReceived() {
        nativeExitReceived = true
    }

    /** An exit callback alone is insufficient: its native view still covers the Activity. */
    fun onNativeRemoved(): Action {
        nativeExitReceived = true
        nativeRemoved = true
        return scheduleWhenReady()
    }

    fun onNextFrame(animatorsEnabled: Boolean): Action {
        if (isComplete || !fadeScheduled || fadeStarted) return Action.NONE
        if (!animatorsEnabled) return finish()
        fadeStarted = true
        return Action.START_FADE
    }

    /** Maximum lifetime for an OEM that never delivers the native exit callback. */
    fun onMissingNativeExit(): Action {
        if (!awaitsNativeCallback) return Action.NONE
        return finish()
    }

    fun finish(): Action {
        if (isComplete) return Action.NONE
        isComplete = true
        return Action.FINISH
    }

    private fun scheduleWhenReady(): Action {
        if (isComplete || fadeScheduled || !contentDrawn || !nativeRemoved) return Action.NONE
        fadeScheduled = true
        return Action.SCHEDULE_FADE
    }
}
