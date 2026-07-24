package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.LuoShuViewModel
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontStudioRoute(
    style: UiStyle,
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    val studioViewModel: LuoShuViewModel = viewModel()
    val latestActions by rememberUpdatedState(actions)
    var showCompositePreview by remember { mutableStateOf(false) }
    var showProfileTransfer by remember { mutableStateOf(false) }
    var showGlyphBrowser by remember { mutableStateOf(false) }
    val stableActions = remember(studioViewModel) {
        FontStudioActions(
            refresh = { latestActions.refresh() },
            pickSlot = { latestActions.pickSlot(it) },
            updateFont = studioViewModel::updateMixFont,
            updateWeight = { slot, weight -> latestActions.updateWeight(slot, weight) },
            updateAxis = { slot, tag, value -> latestActions.updateAxis(slot, tag, value) },
            inspectCoverage = { latestActions.inspectCoverage(it) },
            startMix = { latestActions.startMix() },
            applyDirect = { latestActions.applyDirect(it) },
        )
    }

    Box(Modifier.fillMaxSize()) {
        when (style) {
            UiStyle.MATERIAL -> FontStudioScreenMaterial(state, stableActions)
            UiStyle.MIUIX -> FontStudioScreenMiuix(state, stableActions)
        }
        StudioToolLauncherRow(
            style = style,
            enabled = state.hasFonts && !state.loading,
            onPreview = { showCompositePreview = true },
            onProfile = { showProfileTransfer = true },
            onGlyphs = { showGlyphBrowser = true },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(horizontal = 18.dp, vertical = 96.dp),
        )
    }

    if (showCompositePreview) {
        StudioCompositePreviewDialog(
            style = style,
            state = state,
            onApplyPreset = { preset ->
                latestActions.updateWeight(MixSlot.Cjk, preset.weightFor(MixSlot.Cjk))
                latestActions.updateWeight(MixSlot.Latin, preset.weightFor(MixSlot.Latin))
                latestActions.updateWeight(MixSlot.Digit, preset.weightFor(MixSlot.Digit))
            },
            onDismiss = { showCompositePreview = false },
        )
    }
    if (showProfileTransfer) {
        StudioProfileTransferDialog(
            style = style,
            state = state,
            actions = stableActions,
            onDismiss = { showProfileTransfer = false },
        )
    }
    if (showGlyphBrowser) {
        StudioGlyphBrowserDialog(
            style = style,
            state = state,
            onDismiss = { showGlyphBrowser = false },
        )
    }
}
