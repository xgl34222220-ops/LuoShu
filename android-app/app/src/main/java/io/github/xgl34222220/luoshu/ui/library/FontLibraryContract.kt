package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.LuoShuViewModel
import io.github.xgl34222220.luoshu.ModuleSnapshot

internal enum class FontLibraryFilter(val label: String) {
    ALL("全部"),
    FAVORITE("收藏"),
    VARIABLE("可变字体"),
    MULTI_WEIGHT("多字重"),
    CONFLICT("重复 / 冲突"),
    INVALID("需检查"),
}

internal enum class FontLibrarySort(val label: String) {
    ACTIVE_FIRST("使用优先"),
    FAVORITE_FIRST("收藏优先"),
    NAME("名称"),
    NEWEST("最近导入"),
}

@Immutable
internal data class FontLibraryUiState(
    val loading: Boolean = false,
    val operationBusy: Boolean = false,
    val operationRunning: Boolean = false,
    val query: String = "",
    val error: String = "",
    val operationMessage: String = "",
    val activeFontId: String = "default",
    val fonts: List<FontItem> = emptyList(),
    val allFonts: List<FontItem> = emptyList(),
    val totalCount: Int = 0,
    val validCount: Int = 0,
    val variableCount: Int = 0,
    val multiWeightCount: Int = 0,
    val visibleCount: Int = 0,
    val filter: FontLibraryFilter = FontLibraryFilter.ALL,
    val sort: FontLibrarySort = FontLibrarySort.ACTIVE_FIRST,
)

/** A blocked Root action is not evidence that a font operation is running. */
internal data class FontLibraryAccessState(
    val actionsBlocked: Boolean,
    val operationRunning: Boolean,
    val error: String,
)

internal fun fontLibraryAccessState(
    snapshot: ModuleSnapshot,
    operationBusy: Boolean,
    mixBusy: Boolean,
): FontLibraryAccessState {
    val checking = snapshot.loading || snapshot.statusCached
    val unavailable = !snapshot.installed || !snapshot.rootGranted
    val running = operationBusy || mixBusy
    return FontLibraryAccessState(
        actionsBlocked = running || checking || unavailable,
        operationRunning = running,
        error = if (!checking && unavailable) snapshot.error.ifBlank {
            if (!snapshot.rootGranted) "请为洛书授予 Root 权限，并确认配套模块已启用。"
            else "请先刷入配套的洛书模块，并完整重启手机。"
        } else "",
    )
}

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
    favoriteIds: Set<String> = emptySet(),
    issueIds: Set<String> = emptySet(),
): FontLibraryUiState {
    val filtered = fonts.filter { font ->
        when (selectedFilter) {
            FontLibraryFilter.ALL -> true
            FontLibraryFilter.FAVORITE -> font.id in favoriteIds
            FontLibraryFilter.VARIABLE -> font.valid && font.variable
            FontLibraryFilter.MULTI_WEIGHT -> font.valid && !font.variable && font.weights.size >= 2
            FontLibraryFilter.CONFLICT -> font.id in issueIds
            FontLibraryFilter.INVALID -> !font.valid
        }
    }
    val sorted = when (selectedSort) {
        FontLibrarySort.ACTIVE_FIRST -> filtered.sortedWith(
            compareByDescending<FontItem> { it.id == activeFontId }
                .thenByDescending { it.id in favoriteIds }
                .thenBy { it.name.lowercase() }
                .thenBy { it.id },
        )
        FontLibrarySort.FAVORITE_FIRST -> filtered.sortedWith(
            compareByDescending<FontItem> { it.id in favoriteIds }
                .thenByDescending { it.id == activeFontId }
                .thenBy { it.name.lowercase() }
                .thenBy { it.id },
        )
        FontLibrarySort.NAME -> filtered.sortedWith(
            compareBy<FontItem> { it.name.lowercase() }
                .thenBy { it.id },
        )
        FontLibrarySort.NEWEST -> filtered.sortedWith(
            compareByDescending<FontItem> { it.date }
                .thenByDescending { it.id in favoriteIds }
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
    val failedSwitchMessage = snapshot.taskMessage.takeIf {
        snapshot.taskType == "switch" && snapshot.taskState == "failed" && it.isNotBlank()
    }.orEmpty()
    val access = fontLibraryAccessState(snapshot, operationBusy, mixState.busy)
    return FontLibraryUiState(
        loading = fontLoading || fontRefreshing,
        operationBusy = access.actionsBlocked,
        operationRunning = access.operationRunning,
        query = searchQuery,
        error = access.error.ifBlank { fontError.ifBlank { failedSwitchMessage } },
        operationMessage = if (failedSwitchMessage.isBlank()) operationMessage else "",
        activeFontId = snapshot.activeFont,
        fonts = visibleFonts,
        allFonts = allFonts,
        totalCount = allFonts.size,
        validCount = allFonts.count { it.valid },
        variableCount = allFonts.count { it.variable },
        multiWeightCount = allFonts.count { !it.variable && it.weights.size >= 2 },
        visibleCount = visibleFonts.size,
    )
}
