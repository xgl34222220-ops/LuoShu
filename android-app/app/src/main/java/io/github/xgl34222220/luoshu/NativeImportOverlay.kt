package io.github.xgl34222220.luoshu

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
    embedded: Boolean = false,
) {
    val importViewModel = rememberNativeImportViewModel()
    val state = importViewModel.state
    var expanded by remember { mutableStateOf(false) }

    LaunchedEffect(embedded, state.busy, state.paused) {
        expanded = embedded || state.busy || state.paused
    }

    LaunchedEffect(state.refreshToken) {
        if (state.refreshToken > 0L) viewModel.refreshFonts(force = true)
    }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        importViewModel.startImport(uris)
    }

    val importEnabled = viewModel.snapshot.installed &&
        !viewModel.operationBusy &&
        !viewModel.mixState.busy &&
        (!state.busy || state.paused)
    val onImport = {
        if (state.paused) {
            importViewModel.resumeImport()
        } else {
            launcher.launch(arrayOf("*/*"))
        }
    }

    when (style) {
        UiStyle.MIUIX -> NativeImportOverlayMiuix(
            state = state,
            expanded = expanded,
            enabled = importEnabled,
            embedded = embedded,
            onImport = onImport,
            modifier = modifier,
        )
        UiStyle.MATERIAL -> NativeImportOverlayMaterial(
            viewModel = viewModel,
            state = state,
            expanded = expanded,
            enabled = importEnabled,
            embedded = embedded,
            onImport = onImport,
            modifier = modifier,
        )
    }

    if (state.resultVisible) {
        when (style) {
            UiStyle.MIUIX -> ImportResultDialogMiuix(
                state = state,
                onDismiss = importViewModel::dismissResult,
            )
            UiStyle.MATERIAL -> ImportResultDialogMaterial(
                state = state,
                onDismiss = importViewModel::dismissResult,
            )
        }
    }
}
