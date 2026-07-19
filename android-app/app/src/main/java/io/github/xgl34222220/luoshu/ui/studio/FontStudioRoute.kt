package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.runtime.Composable
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontStudioRoute(
    style: UiStyle,
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    when (style) {
        UiStyle.MATERIAL -> FontStudioScreenMaterial(state, actions)
        UiStyle.MIUIX -> FontStudioScreenMiuix(state, actions)
    }
}
