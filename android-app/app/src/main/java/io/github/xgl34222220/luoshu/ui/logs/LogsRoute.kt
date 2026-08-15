package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.rememberNativeImportViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import kotlinx.coroutines.launch

@Composable
internal fun LogsRoute(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
) {
    val importViewModel = rememberNativeImportViewModel()
    val importState = importViewModel.state
    val displayState = state.withNativeImport(importState)
    val scope = rememberCoroutineScope()
    var diagnosticState by remember { mutableStateOf(DiagnosticExportState()) }
    val onDiagnostic = {
        if (!diagnosticState.busy) {
            diagnosticState = DiagnosticExportState(busy = true)
            scope.launch {
                diagnosticState = exportSanitizedDiagnostic()
            }
        }
    }

    Box(
        Modifier
            .fillMaxSize()
            .padding(bottom = 8.dp),
    ) {
        LogsScreenCompact(
            style = style,
            state = displayState,
            actions = actions,
            diagnosticState = diagnosticState,
            onDiagnostic = onDiagnostic,
        )
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
                .padding(horizontal = 14.dp, vertical = 12.dp),
        )
    }

    if (diagnosticState.resultVisible) {
        DiagnosticExportDialog(
            style = style,
            state = diagnosticState,
            onDismiss = { diagnosticState = DiagnosticExportState() },
        )
    }
}
