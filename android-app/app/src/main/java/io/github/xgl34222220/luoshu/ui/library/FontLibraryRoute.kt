package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
) {
    var filter by rememberSaveable { mutableStateOf(FontLibraryFilter.ALL) }
    var sort by rememberSaveable { mutableStateOf(FontLibrarySort.ACTIVE_FIRST) }
    val displayState = remember(state, filter, sort) {
        state.forDisplay(filter, sort)
    }
    val displayActions = remember(actions) {
        actions.copy(
            setFilter = { filter = it },
            setSort = { sort = it },
        )
    }

    when (style) {
        UiStyle.MATERIAL -> FontLibraryScreenMaterial(displayState, displayActions)
        UiStyle.MIUIX -> FontLibraryScreenMiuix(displayState, displayActions)
    }
}