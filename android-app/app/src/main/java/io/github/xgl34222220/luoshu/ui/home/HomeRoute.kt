package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
        var attempt = 0
        while (latest.level == DeviceTrustLevel.PENDING && attempt < 9 && !state.taskRunning) {
            delay(5_000L)
            latest = loadDeviceTrustState()
            trustState = latest
            attempt += 1
        }
    }

    val trustContent: @Composable () -> Unit = {
        if (state.moduleInstalled) {
            DeviceTrustChip(
                style = style,
                state = trustState,
                onClick = { showTrustDetails = true },
            )
        }
    }

    when (style) {
        UiStyle.MIUIX -> HomeScreenMiuix(
            state = state,
            actions = actions,
            trustContent = trustContent,
        )
        UiStyle.MATERIAL -> HomeScreenCompact(
            style = style,
            state = state,
            actions = actions,
            trustContent = trustContent,
        )
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
