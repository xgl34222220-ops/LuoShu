package io.github.xgl34222220.luoshu.ui.launch

/** Completion is one-shot; system-layer cleanup remains mandatory even after completion. */
internal class LuoShuLaunchExitPolicy {
    enum class Action { NONE, REMOVE_NATIVE, FINISH }

    var isComplete: Boolean = false
        private set

    // No native-callback watchdog or animation gate can hold the actual App page.
    fun onNativeExit(): Action = Action.REMOVE_NATIVE

    fun onContentDrawn(): Action = finish()

    fun finish(): Action {
        if (isComplete) return Action.NONE
        isComplete = true
        return Action.FINISH
    }
}
