package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/** Constructor-safe restoration: callers assign this Job before explicitly starting it. */
internal fun CoroutineScope.createFontCacheRestore(restore: suspend () -> Unit): Job =
    launch(start = CoroutineStart.LAZY) { restore() }
