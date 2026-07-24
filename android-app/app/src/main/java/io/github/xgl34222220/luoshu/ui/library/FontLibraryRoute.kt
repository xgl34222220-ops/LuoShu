package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
    val context = LocalContext.current
    val collectionStore = remember(context.applicationContext) {
        FontLibraryCollectionStore(context.applicationContext)
    }
    var collections by remember { mutableStateOf(collectionStore.load()) }
    var filter by rememberSaveable { mutableStateOf(FontLibraryFilter.ALL) }
    var sort by rememberSaveable { mutableStateOf(FontLibrarySort.ACTIVE_FIRST) }
    var detailFont by remember { mutableStateOf<FontItem?>(null) }
    var showManagement by rememberSaveable { mutableStateOf(false) }
    val latestActions by rememberUpdatedState(actions)
    val conflicts = remember(state.fonts) { analyzeFontLibraryConflicts(state.fonts) }
    val displayState = remember(state, filter, sort, collections.favoriteIds, conflicts.issueIds) {
        state.forDisplay(
            selectedFilter = filter,
            selectedSort = sort,
            favoriteIds = collections.favoriteIds,
            issueIds = conflicts.issueIds,
        )
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

    fun persistCollections(next: FontLibraryCollections) {
        collections = next
        collectionStore.save(next)
    }

    val combinedTopActions: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            topActions()
            FontLibraryUtilitiesBar(
                style = style,
                fonts = state.allFonts,
                collections = collections,
                enabled = !state.loading && !state.operationBusy,
                onCollectionsChange = ::persistCollections,
            )
        }
    }

    Box(Modifier.fillMaxSize()) {
        when (style) {
            UiStyle.MATERIAL -> FontLibraryScreenMaterial(displayState, displayActions, combinedTopActions)
            UiStyle.MIUIX -> FontLibraryScreenMiuix(displayState, displayActions, combinedTopActions)
        }
        FontLibraryManagementButton(
            style = style,
            favoriteCount = collections.favoriteIds.size,
            issueCount = conflicts.issueIds.size,
            loading = state.loading,
            onClick = { showManagement = true },
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(end = 18.dp, bottom = 18.dp),
        )
    }

    if (showManagement) {
        FontLibraryManagementDialog(
            style = style,
            fonts = state.fonts,
            activeFontId = state.activeFontId,
            collections = collections,
            conflicts = conflicts,
            onCollectionsChange = { visibleNext ->
                val visibleIds = state.fonts.map { it.id }.toSet()
                val merged = FontLibraryCollections(
                    favoriteIds = (collections.favoriteIds - visibleIds) + visibleNext.favoriteIds,
                    tags = collections.tags.filterKeys { it !in visibleIds } + visibleNext.tags,
                )
                persistCollections(merged)
            },
            onOpenDetails = { font ->
                showManagement = false
                detailFont = font
            },
            onDismiss = { showManagement = false },
        )
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
