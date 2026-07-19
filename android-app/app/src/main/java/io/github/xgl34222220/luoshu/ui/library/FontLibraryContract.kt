package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.LuoShuViewModel

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
)

internal data class FontLibraryActions(
    val refresh: () -> Unit,
    val setQuery: (String) -> Unit,
    val apply: (FontItem) -> Unit,
    val delete: (FontItem) -> Unit,
    val restoreDefault: () -> Unit,
)

internal fun LuoShuViewModel.toFontLibraryUiState(): FontLibraryUiState = FontLibraryUiState(
    loading = fontLoading,
    operationBusy = operationBusy || mixState.busy,
    query = searchQuery,
    error = fontError,
    operationMessage = operationMessage,
    activeFontId = snapshot.activeFont,
    fonts = filteredFonts,
    totalCount = fonts.size,
    validCount = fonts.count { it.valid },
    variableCount = fonts.count { it.variable },
    multiWeightCount = fonts.count { !it.variable && it.weights.size >= 2 },
)
