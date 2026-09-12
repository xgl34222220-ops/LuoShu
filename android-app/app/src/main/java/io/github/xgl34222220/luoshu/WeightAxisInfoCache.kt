package io.github.xgl34222220.luoshu

import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Keep one successful revision per family; transient failures remain retryable. */
internal class WeightAxisInfoCache {
    private data class Entry(val source: FontItem, val info: WeightAxisInfo)

    private val entries = ConcurrentHashMap<String, Entry>()
    private val locks = ConcurrentHashMap<String, Mutex>()

    fun get(font: FontItem): WeightAxisInfo? =
        entries[font.id]?.takeIf { font.sourceRevision.isNotBlank() && it.source == font }?.info

    suspend fun load(font: FontItem, loader: suspend (FontItem) -> WeightAxisInfo): WeightAxisInfo =
        locks.computeIfAbsent(font.id) { Mutex() }.withLock {
            // sourceRevision includes exact sizes and full mtimes from the existing directory
            // fingerprint. Older bridges without that identity get no persistent axis cache.
            get(font) ?: loader(font).also { info ->
                if (!info.loading && info.error.isBlank() && font.sourceRevision.isNotBlank()) {
                    entries[font.id] = Entry(font, info)
                }
            }
        }
}
