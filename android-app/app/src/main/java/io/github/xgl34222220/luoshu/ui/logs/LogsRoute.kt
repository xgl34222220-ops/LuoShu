package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.rememberNativeImportViewModel
import io.github.xgl34222220.luoshu.NativeImportPhase
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import kotlinx.coroutines.launch

@Composable
internal fun LogsRoute(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
    onBack: () -> Unit,
) {
    val importViewModel = rememberNativeImportViewModel()
    val importState = importViewModel.state
    val displayState = state.withNativeImport(importState)
    val density = LocalDensity.current
    var importControlsHeight by remember { mutableIntStateOf(0) }
    val hasImportControls = importState.taskId.isNotBlank() && importState.phase != NativeImportPhase.IDLE
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
            .navigationBarsPadding()
            .padding(bottom = 8.dp),
    ) {
        LogsScreenCompact(
            style = style,
            state = displayState,
            actions = actions,
            diagnosticState = diagnosticState,
            onDiagnostic = onDiagnostic,
            onBack = onBack,
            controlsBottomPadding = if (hasImportControls) with(density) { importControlsHeight.toDp() } else 0.dp,
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
                .onSizeChanged { importControlsHeight = it.height }
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
