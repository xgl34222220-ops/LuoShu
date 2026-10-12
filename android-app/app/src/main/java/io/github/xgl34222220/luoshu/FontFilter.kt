package io.github.xgl34222220.luoshu

internal fun filterFonts(fonts: List<FontItem>, rawQuery: String): List<FontItem> {
    val query = rawQuery.trim()
    if (query.isEmpty()) return fonts
    return fonts.filter { item ->
        item.name.contains(query, ignoreCase = true) ||
            item.id.contains(query, ignoreCase = true) ||
            item.format.contains(query, ignoreCase = true)
    }
}

/** Caches the last filter result by font-list identity and query (fonts is replaced, never mutated). */
internal class FontFilterMemo(private val filter: (List<FontItem>, String) -> List<FontItem> = ::filterFonts) {
    private var lastFonts: List<FontItem>? = null
    private var lastQuery: String? = null
    private var lastResult: List<FontItem> = emptyList()

    @Synchronized
    fun filter(fonts: List<FontItem>, query: String): List<FontItem> {
        if (fonts === lastFonts && query == lastQuery) return lastResult
        val result = filter.invoke(fonts, query)
        lastFonts = fonts
        lastQuery = query
        lastResult = result
        return result
    }
}
