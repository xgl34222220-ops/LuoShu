package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
    var filter by rememberSaveable { mutableStateOf(FontLibraryFilter.ALL) }
    var sort by rememberSaveable { mutableStateOf(FontLibrarySort.ACTIVE_FIRST) }
    var detailFont by remember { mutableStateOf<FontItem?>(null) }
    val latestActions by rememberUpdatedState(actions)
    val displayState = remember(state, filter, sort) {
        state.forDisplay(filter, sort)
    }
    val displayActions = remember {
        FontLibraryActions(
            refresh = { latestActions.refresh() },
            setQuery = { latestActions.setQuery(it) },
            apply = { latestActions.apply(it) },
            delete = { latestActions.delete(it) },
            restoreDefault = { latestActions.restoreDefault() },
            details = { detailFont = it },
            setFilter = { filter = it },
            setSort = { sort = it },
        )
    }

    when (style) {
        UiStyle.MATERIAL -> FontLibraryScreenMaterial(displayState, displayActions, topActions)
        UiStyle.MIUIX -> FontLibraryScreenMiuix(displayState, displayActions, topActions)
    }

    detailFont?.let { font ->
        FontDetailsDialogRoute(
            style = style,
            font = font,
            active = state.activeFontId == font.id,
            busy = state.operationBusy,
            onDismiss = { detailFont = null },
            onApply = {
                detailFont = null
                latestActions.apply(font)
            },
        )
    }
}
