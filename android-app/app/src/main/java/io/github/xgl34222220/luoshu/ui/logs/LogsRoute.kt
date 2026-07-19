package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.NativeImportViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun LogsRoute(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
) {
    val importViewModel: NativeImportViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val importState = importViewModel.state
    val displayState = state.withNativeImport(importState)

    Box(Modifier.fillMaxSize()) {
        when (style) {
            UiStyle.MATERIAL -> LogsScreenMaterial(displayState, actions)
            UiStyle.MIUIX -> LogsScreenMiuix(displayState, actions)
        }
        ImportTaskControls(
            style = style,
            state = importState,
            onPause = importViewModel::pauseImport,
            onResume = importViewModel::resumeImport,
            onCancel = importViewModel::cancelImport,
            onRetry = importViewModel::retryFailed,
            onClear = importViewModel::clearRecord,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(horizontal = 14.dp, vertical = 94.dp),
        )
    }
}
