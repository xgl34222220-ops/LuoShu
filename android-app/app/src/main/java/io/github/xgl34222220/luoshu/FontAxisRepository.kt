package io.github.xgl34222220.luoshu

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Share successful metadata by source revision; failures and cancellation remain retryable. */
internal class FontAxisRepository(private val maxEntries: Int = 64) {
    init { require(maxEntries > 0) }

    private val entries = LinkedHashMap<String, WeightAxisInfo>(16, .75f, true)
    private val loadLock = Mutex()
    private val successfulEntries = MutableStateFlow<Map<String, WeightAxisInfo>>(emptyMap())
    val successes = successfulEntries.asStateFlow()

    fun cached(revision: String): WeightAxisInfo? = synchronized(entries) { entries[revision] }

    suspend fun resolve(revision: String, load: suspend () -> WeightAxisInfo): WeightAxisInfo {
        cached(revision)?.let { return it }
        // Axis readers are short foreground work. A single lock also bounds concurrent
        // root/Python readers when the same source is shown in several slots.
        return loadLock.withLock {
            cached(revision) ?: load().also { info ->
                if (!info.loading && info.error.isBlank()) synchronized(entries) {
                    entries[revision] = info
                    while (entries.size > maxEntries) entries.remove(entries.keys.first())
                    // Publish an immutable snapshot so existing controls can recover when
                    // another caller successfully retries the same source revision.
                    successfulEntries.value = entries.toMap()
                }
            }
        }
    }
}
