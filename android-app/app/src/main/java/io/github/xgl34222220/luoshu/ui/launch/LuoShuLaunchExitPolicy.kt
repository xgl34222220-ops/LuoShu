package io.github.xgl34222220.luoshu.ui.launch

/** One-shot content completion; the platform owns native splash removal. */
internal class LuoShuLaunchExitPolicy {
    enum class Action { NONE, FINISH }

    var isComplete: Boolean = false
        private set

    fun onContentDrawn(): Action = finish()

    fun finish(): Action {
        if (isComplete) return Action.NONE
        isComplete = true
        return Action.FINISH
    }
}
