package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.runtime.Composable
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontLibraryRoute(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
) {
    when (style) {
        UiStyle.MATERIAL -> FontLibraryScreenMaterial(state, actions)
        UiStyle.MIUIX -> FontLibraryScreenMiuix(state, actions)
    }
}
