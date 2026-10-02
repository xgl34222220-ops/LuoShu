package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInVertically
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.withFrameNanos
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.FontLoadDiagnostics
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
    LaunchedEffect(state.loading, state.totalCount, state.verified) {
        if (!state.loading) {
            // A composed list is not a presented frame. Wait across a frame boundary before
            // reporting the observation; this remains an App signal, not a GPU timing claim.
            withFrameNanos { }
            withFrameNanos { }
            FontLoadDiagnostics.mark("library_frame", state.totalCount, state.verified)
        }
    }
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

    val managementTools: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            StaggeredManagementItem(index = 0) {
                topActions()
            }
            StaggeredManagementItem(index = 1) {
                FontLibraryUtilitiesBar(
                    style = style,
                    fonts = state.allFonts,
                    collections = collections,
                    enabled = !state.loading && !state.operationBusy && state.verified,
                    onCollectionsChange = ::persistCollections,
                )
            }
            StaggeredManagementItem(index = 2) {
                FontArchiveExportTool(
                    style = style,
                    fonts = state.allFonts,
                    collections = collections,
                    enabled = !state.loading && !state.operationBusy && state.verified,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            StaggeredManagementItem(index = 3) {
                FontLibraryManagementButton(
                    style = style,
                    favoriteCount = collections.favoriteIds.size,
                    issueCount = conflicts.issueIds.size,
                    loading = state.loading,
                    onClick = { showManagement = true },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }

    LaunchedEffect(state.allFonts) {
        if (detailFont != null && state.allFonts.none { it.id == detailFont?.id }) detailFont = null
    }
    val childLayerActive = showManagement || detailFont?.let { selected ->
        state.allFonts.any { it.id == selected.id }
    } == true
    val pageScale by animateFloatAsState(
        targetValue = if (childLayerActive) .96f else 1f,
        animationSpec = spring(dampingRatio = .86f, stiffness = Spring.StiffnessMediumLow),
        label = "fontLibraryDepthScale",
    )
    Box(
        modifier = Modifier.graphicsLayer {
            scaleX = pageScale
            scaleY = pageScale
        },
    ) {
        FontLibraryScreenCompact(
            style = style,
            state = displayState,
            actions = displayActions,
            tools = managementTools,
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

    detailFont?.let { selected ->
        val font = state.allFonts.firstOrNull { it.id == selected.id } ?: return@let
        FontDetailsDialogRoute(
            style = style,
            font = font,
            active = state.activeFontId == font.id,
            busy = state.operationBusy || !state.verified,
            onDismiss = { detailFont = null },
            onApply = {
                detailFont = null
                latestActions.apply(font)
            },
        )
    }
}


@Composable
private fun StaggeredManagementItem(
    index: Int,
    content: @Composable () -> Unit,
) {
    val visible = remember(index) {
        MutableTransitionState(false).apply { targetState = true }
    }
    val delay = index.coerceAtLeast(0) * 30
    AnimatedVisibility(
        visibleState = visible,
        enter = fadeIn(animationSpec = tween(durationMillis = 180, delayMillis = delay)) +
            slideInVertically(
                animationSpec = tween(durationMillis = 220, delayMillis = delay),
                initialOffsetY = { it / 5 },
            ),
    ) {
        content()
    }
}
