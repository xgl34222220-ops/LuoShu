package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.runtime.Composable
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun LogsRoute(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
) {
    when (style) {
        UiStyle.MATERIAL -> LogsScreenMaterial(state, actions)
        UiStyle.MIUIX -> LogsScreenMiuix(state, actions)
    }
}
