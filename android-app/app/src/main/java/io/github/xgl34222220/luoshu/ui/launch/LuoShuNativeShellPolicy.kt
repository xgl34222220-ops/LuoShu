package io.github.xgl34222220.luoshu.ui.launch

/** One Activity instance, one forward-only handoff. Submission is not presentation. */
internal class LuoShuNativeShellPolicy {
    enum class Phase { SHELL, SHELL_SUBMITTED, CONTENT, DISPOSED }
    var phase = Phase.SHELL
        private set

    fun onShellSubmitted(): Boolean {
        if (phase != Phase.SHELL) return false
        phase = Phase.SHELL_SUBMITTED
        return true
    }

    fun beginContent(softwareFallback: Boolean = false): Boolean {
        if (phase != Phase.SHELL_SUBMITTED && !(softwareFallback && phase == Phase.SHELL)) return false
        phase = Phase.CONTENT
        return true
    }

    fun dispose() { phase = Phase.DISPOSED }

    companion object {
        fun eligible(api: Int, restored: Boolean, taskEntry: Boolean): Boolean =
            api >= 31 && !restored && !taskEntry
    }
}
