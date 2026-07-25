package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import kotlinx.coroutines.delay

@Composable
fun HomeRoute(
    style: UiStyle,
    state: HomeUiState,
    actions: HomeActions,
) {
    var trustState by remember { mutableStateOf(DeviceTrustState()) }
    var showTrustDetails by remember { mutableStateOf(false) }
    var showAcceptanceGuide by remember { mutableStateOf(false) }
    var trustRefreshGeneration by remember { mutableIntStateOf(0) }

    LaunchedEffect(
        state.moduleInstalled,
        state.currentFont,
        state.rebootRequired,
        state.taskRunning,
        trustRefreshGeneration,
    ) {
        if (!state.moduleInstalled) {
            trustState = DeviceTrustState(loading = false, error = "请先安装洛书模块")
            return@LaunchedEffect
        }

        var latest = loadDeviceTrustState()
        trustState = latest
        // The late-start verifier can finish shortly after the App becomes interactive.
        // Refresh a bounded number of times so Home does not keep a stale pending chip until
        // the user manually leaves the page or presses refresh.
        var attempt = 0
        while (latest.level == DeviceTrustLevel.PENDING && attempt < 9 && !state.taskRunning) {
            delay(5_000L)
            latest = loadDeviceTrustState()
            trustState = latest
            attempt += 1
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
                    .navigationBarsPadding()
                    .padding(start = 18.dp, end = 18.dp, bottom = 108.dp),
            )
        }
    }

    if (showTrustDetails) {
        DeviceTrustDialog(
            style = style,
            state = trustState,
            onDismiss = { showTrustDetails = false },
            onOpenAcceptance = { showAcceptanceGuide = true },
        )
    }
    if (showAcceptanceGuide) {
        DeviceAcceptanceGuideDialog(
            style = style,
            state = state,
            trust = trustState,
            onRefresh = {
                actions.refresh()
                trustRefreshGeneration += 1
            },
            onReboot = actions.reboot,
            onDismiss = { showAcceptanceGuide = false },
        )
    }
}
