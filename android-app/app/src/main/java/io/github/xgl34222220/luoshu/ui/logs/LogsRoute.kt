package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.navigation.LuoShuTab

@Composable
internal fun LogsRoute(
    style: UiStyle,
    state: LogsUiState,
    actions: LogsActions,
    importState: NativeImportTaskCenterState = NativeImportTaskCenterState(),
    importActions: NativeImportTaskCenterActions = NativeImportTaskCenterActions(),
    onNavigate: (LuoShuTab) -> Unit,
) {
    var diagnosticState by remember { mutableStateOf(DiagnosticExportState()) }
    LaunchedEffect(state.logs) {
        if (state.logs == "尚未读取日志") actions.refresh()
    }
    Box {
        when (style) {
            UiStyle.MATERIAL -> LogsScreenMaterial(
                state = state,
                actions = actions,
                importState = importState,
                importActions = importActions,
                onNavigate = onNavigate,
            )
            UiStyle.MIUIX -> LogsScreenMiuix(
                state = state,
                actions = actions,
                importState = importState,
                importActions = importActions,
                onNavigate = onNavigate,
            )
        }
        // MIUIx 标题区本身高于普通工具栏；让诊断与刷新按钮共用同一视觉中线。
        DiagnosticExportButton(
            style = style,
            state = diagnosticState,
            onClick = {
                if (diagnosticState.busy) return@DiagnosticExportButton
                diagnosticState = DiagnosticExportState(busy = true)
            },
            modifier = Modifier
                .align(Alignment.TopEnd)
                .padding(
                    top = if (style == UiStyle.MIUIX) 25.dp else 14.dp,
                    end = 82.dp,
                ),
        )
    }
    LaunchedEffect(diagnosticState.busy) {
        if (!diagnosticState.busy) return@LaunchedEffect
        diagnosticState = exportSanitizedDiagnostic()
    }
    if (diagnosticState.resultVisible) {
        DiagnosticExportDialog(
            style = style,
            state = diagnosticState,
            onDismiss = { diagnosticState = DiagnosticExportState() },
        )
    }
}
