package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.runtime.Composable
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
fun HomeRoute(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
) {
    when (style) {
        UiStyle.MATERIAL -> HomeScreenMaterial(state, actions)
        UiStyle.MIUIX -> HomeScreenMiuix(state, actions)
    }
}
