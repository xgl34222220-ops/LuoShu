package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.runtime.Composable
import io.github.xgl34222220.luoshu.NativeImportViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun LogsRoute(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
) {
    val importViewModel: NativeImportViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val displayState = state.withNativeImport(importViewModel.state)
    when (style) {
        UiStyle.MATERIAL -> LogsScreenMaterial(displayState, actions)
        UiStyle.MIUIX -> LogsScreenMiuix(displayState, actions)
    }
}
