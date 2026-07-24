package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
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

@Composable
fun HomeRoute(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
) {
    var trustState by remember { mutableStateOf(DeviceTrustState()) }
    var showTrustDetails by remember { mutableStateOf(false) }

    LaunchedEffect(
        state.moduleInstalled,
        state.currentFont,
        state.rebootRequired,
        state.taskRunning,
    ) {
        trustState = if (state.moduleInstalled) {
            loadDeviceTrustState()
        } else {
            DeviceTrustState(loading = false, error = "请先安装洛书模块")
        }
    }

    Box(Modifier.fillMaxSize()) {
        when (style) {
            UiStyle.MATERIAL -> HomeScreenMaterial(state, actions)
            UiStyle.MIUIX -> HomeScreenMiuix(state, actions)
        }
        if (state.moduleInstalled) {
            DeviceTrustChip(
                style = style,
                state = trustState,
                onClick = { showTrustDetails = true },
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(horizontal = 18.dp, vertical = 96.dp),
            )
        }
    }

    if (showTrustDetails) {
        DeviceTrustDialog(
            style = style,
            state = trustState,
            onDismiss = { showTrustDetails = false },
        )
    }
}
