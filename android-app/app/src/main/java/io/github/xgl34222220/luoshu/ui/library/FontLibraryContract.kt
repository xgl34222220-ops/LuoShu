package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.LuoShuViewModel

internal enum class FontLibraryFilter(val label: String) {
    ALL("全部"),
    VARIABLE("可变字体"),
    MULTI_WEIGHT("多字重"),
    INVALID("需检查"),
}

internal enum class FontLibrarySort(val label: String) {
    ACTIVE_FIRST("使用优先"),
    NAME("名称"),
    NEWEST("最近导入"),
}

@Immutable
internal data class FontLibraryUiState(
    val loading: Boolean = false,
    val operationBusy: Boolean = false,
    val query: String = "",
    val error: String = "",
    val operationMessage: String = "",
    val activeFontId: String = "default",
    val fonts: List<FontItem> = emptyList(),
    val totalCount: Int = 0,
    val validCount: Int = 0,
    val variableCount: Int = 0,
    val multiWeightCount: Int = 0,
    val visibleCount: Int = 0,
    val filter: FontLibraryFilter = FontLibraryFilter.ALL,
    val sort: FontLibrarySort = FontLibrarySort.ACTIVE_FIRST,
)

@Immutable
internal data class FontLibraryActions(
    val refresh: () -> Unit,
    val setQuery: (String) -> Unit,
    val apply: (FontItem) -> Unit,
    val delete: (FontItem) -> Unit,
    val restoreDefault: () -> Unit,
    val details: (FontItem) -> Unit = {},
    val setFilter: (FontLibraryFilter) -> Unit = {},
    val setSort: (FontLibrarySort) -> Unit = {},
)

internal fun FontLibraryUiState.forDisplay(
    selectedFilter: FontLibraryFilter,
    selectedSort: FontLibrarySort,
): FontLibraryUiState {
    val filtered = fonts.filter { font ->
        when (selectedFilter) {
            FontLibraryFilter.ALL -> true
            FontLibraryFilter.VARIABLE -> font.valid && font.variable
            FontLibraryFilter.MULTI_WEIGHT -> font.valid && !font.variable && font.weights.size >= 2
            FontLibraryFilter.INVALID -> !font.valid
        }
    }
    val sorted = when (selectedSort) {
        FontLibrarySort.ACTIVE_FIRST -> filtered.sortedWith(
            compareByDescending<FontItem> { it.id == activeFontId }
                .thenBy { it.name.lowercase() }
                .thenBy { it.id },
        )
        FontLibrarySort.NAME -> filtered.sortedWith(
            compareBy<FontItem> { it.name.lowercase() }
                .thenBy { it.id },
        )
        FontLibrarySort.NEWEST -> filtered.sortedWith(
            compareByDescending<FontItem> { it.date }
                .thenBy { it.name.lowercase() }
                .thenBy { it.id },
        )
    }
    return copy(
        fonts = sorted,
        visibleCount = sorted.size,
        filter = selectedFilter,
        sort = selectedSort,
    )
}

internal fun LuoShuViewModel.toFontLibraryUiState(): FontLibraryUiState {
    val allFonts = fonts
    val visibleFonts = filteredFonts
    return FontLibraryUiState(
        loading = fontLoading || fontRefreshing,
        operationBusy = operationBusy || mixState.busy,
        query = searchQuery,
        error = fontError,
        operationMessage = operationMessage,
        activeFontId = snapshot.activeFont,
        fonts = visibleFonts,
        totalCount = allFonts.size,
        validCount = allFonts.count { it.valid },
        variableCount = allFonts.count { it.variable },
        multiWeightCount = allFonts.count { !it.variable && it.weights.size >= 2 },
        visibleCount = visibleFonts.size,
    )
}
