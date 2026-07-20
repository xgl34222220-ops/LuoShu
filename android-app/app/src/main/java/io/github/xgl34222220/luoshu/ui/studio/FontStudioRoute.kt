package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontStudioRoute(
    style: UiStyle,
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    val latestActions by rememberUpdatedState(actions)
    val stableActions = remember {
        FontStudioActions(
            refresh = { latestActions.refresh() },
            pickSlot = { latestActions.pickSlot(it) },
            updateWeight = { slot, weight -> latestActions.updateWeight(slot, weight) },
            updateAxis = { slot, tag, value -> latestActions.updateAxis(slot, tag, value) },
            inspectCoverage = { latestActions.inspectCoverage(it) },
            startMix = { latestActions.startMix() },
            applyDirect = { latestActions.applyDirect(it) },
        )
    }
    when (style) {
        UiStyle.MATERIAL -> FontStudioScreenMaterial(state, stableActions)
        UiStyle.MIUIX -> FontStudioScreenMiuix(state, stableActions)
    }
}
