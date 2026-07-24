package io.github.xgl34222220.luoshu.ui.library

/** Keeps pair collections readable when a transformation has already left Map scope. */
internal fun <K, V> Iterable<Pair<K, V>>.filterValues(
    predicate: (V) -> Boolean,
): List<Pair<K, V>> = filter { (_, value) -> predicate(value) }
