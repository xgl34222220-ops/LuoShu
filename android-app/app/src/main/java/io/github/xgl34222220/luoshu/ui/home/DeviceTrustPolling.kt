package io.github.xgl34222220.luoshu.ui.home

import androidx.lifecycle.Lifecycle
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.first

/**
 * Suspends while the host is below STARTED (App in background / screen off) so the expanded
 * trust details stop issuing Root reads until the user can see them again.
 */
internal suspend fun awaitLifecycleStarted(state: StateFlow<Lifecycle.State>) {
    if (state.value.isAtLeast(Lifecycle.State.STARTED)) return
    state.first { it.isAtLeast(Lifecycle.State.STARTED) }
}
