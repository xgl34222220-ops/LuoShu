package io.github.xgl34222220.luoshu

/** Main-thread state for module configuration reads and the user's in-memory draft. */
internal class MixConfigLoadGuard {
    internal data class Request(
        val sequence: Long,
        val draftRevision: Long,
        val mayReplaceDraft: Boolean,
    )

    private var sequence = 0L
    private var draftRevision = 0L
    private var hasDraftEdits = false
    private var initialReadComplete = false
    private var active: Request? = null

    fun begin(force: Boolean): Request? {
        if (active != null || (!force && initialReadComplete)) return null
        return Request(++sequence, draftRevision, force || !hasDraftEdits).also { active = it }
    }

    fun edited() {
        draftRevision += 1L
        hasDraftEdits = true
    }

    /** A verified but superseded response completes initialization without replacing the draft. */
    fun complete(request: Request, allowApply: Boolean = true): Boolean {
        if (active != request) return false
        active = null
        initialReadComplete = true
        val apply = allowApply && request.mayReplaceDraft && request.draftRevision == draftRevision
        if (apply) hasDraftEdits = false
        return apply
    }

    /** Failed/cancelled first reads remain retryable; an older request cannot finish a newer one. */
    fun failed(request: Request): Boolean {
        if (active != request) return false
        active = null
        return true
    }
}
