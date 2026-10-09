package io.github.xgl34222220.luoshu

/** Installed files do not prove the root manager currently enables the module. */
internal fun googleFontMaintenanceEligible(
    loading: Boolean,
    statusCached: Boolean,
    rootGranted: Boolean,
    installed: Boolean,
    enabled: Boolean = false,
): Boolean = !loading && !statusCached && rootGranted && installed && enabled

/** Events may arrive together; one pass owns the request and one pending event. */
internal class GoogleFontMaintenanceGate {
    private var trusted = false
    private var resumed = false
    private var foregroundHandled = false
    private var pendingPackageEvent = false
    private var running = false

    fun update(trusted: Boolean, resumed: Boolean): Boolean {
        this.trusted = trusted
        // A root manager can temporarily pause/resume the Activity during our
        // own request. That transition must never schedule another su request.
        if (!resumed && !running) foregroundHandled = false
        if (resumed && running) foregroundHandled = true
        this.resumed = resumed
        if (!trusted) pendingPackageEvent = false
        return beginIfNeeded()
    }

    fun packageReplaced(): Boolean {
        if (!trusted) return false
        pendingPackageEvent = true
        return beginIfNeeded()
    }

    fun completed(): Boolean {
        running = false
        return beginIfNeeded()
    }

    private fun beginIfNeeded(): Boolean {
        if (!trusted || running) return false
        val foregroundPending = resumed && !foregroundHandled
        if (!foregroundPending && !pendingPackageEvent) return false
        if (foregroundPending) foregroundHandled = true
        pendingPackageEvent = false
        running = true
        return true
    }
}
