package io.github.xgl34222220.luoshu.ui.library

import io.github.xgl34222220.luoshu.FontItem
import org.junit.Assert.assertEquals
import org.junit.Test

class FontLibraryContractTest {
    private val regular = font(id = "regular", name = "Beta", date = "2026-07-17")
    private val variable = font(id = "variable", name = "Alpha", date = "2026-07-18", variable = true)
    private val multi = font(id = "multi", name = "Gamma", date = "2026-07-19", weights = listOf("regular", "bold"))
    private val invalid = font(id = "invalid", name = "Broken", date = "2026-07-20", valid = false)

    private val state = FontLibraryUiState(
        activeFontId = "multi",
        fonts = listOf(regular, variable, multi, invalid),
        totalCount = 4,
    )

    @Test
    fun filtersDoNotMutateTheUnderlyingIndex() {
        assertEquals(listOf("variable"), state.forDisplay(FontLibraryFilter.VARIABLE, FontLibrarySort.NAME).fonts.map { it.id })
        assertEquals(listOf("multi"), state.forDisplay(FontLibraryFilter.MULTI_WEIGHT, FontLibrarySort.NAME).fonts.map { it.id })
        assertEquals(listOf("invalid"), state.forDisplay(FontLibraryFilter.INVALID, FontLibrarySort.NAME).fonts.map { it.id })
        assertEquals(4, state.fonts.size)
    }

    @Test
    fun activeFirstKeepsTheCurrentFontAtTheTop() {
        val result = state.forDisplay(FontLibraryFilter.ALL, FontLibrarySort.ACTIVE_FIRST)
        assertEquals("multi", result.fonts.first().id)
        assertEquals(4, result.visibleCount)
    }

    @Test
    fun newestSortUsesTheImportedDateDescending() {
        val result = state.forDisplay(FontLibraryFilter.ALL, FontLibrarySort.NEWEST)
        assertEquals(listOf("invalid", "multi", "variable", "regular"), result.fonts.map { it.id })
    }

    private fun font(
        id: String,
        name: String,
        date: String,
        variable: Boolean = false,
        valid: Boolean = true,
        weights: List<String> = emptyList(),
    ) = FontItem(
        id = id,
        name = name,
        format = "TTF",
        size = "1 MB",
        date = date,
        variable = variable,
        valid = valid,
        error = if (valid) "" else "损坏",
        weights = weights,
    )
}