package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

private const val STOCK_SCAN_COMMAND =
    "sh /data/adb/modules/LuoShu/common/font_manager.sh action stock_scan"

private fun stockScanResultMessage(stdout: String, stderr: String, code: Int): String {
    val jsonLine = stdout.lineSequence()
        .map { it.trim() }
        .lastOrNull { it.startsWith("{") && it.endsWith("}") }
        ?: stderr.lineSequence().map { it.trim() }.lastOrNull { it.startsWith("{") && it.endsWith("}") }
    val parsed = jsonLine?.let { runCatching { JSONObject(it) }.getOrNull() }
    val message = parsed?.optString("message").orEmpty()
    if (code != 0 || parsed?.optString("status") == "error") {
        return message.ifBlank { stderr.ifBlank { stdout }.trim().ifBlank { "原厂字体扫描失败" } }
    }
    val slots = parsed?.optInt("slotCount", -1) ?: -1
    val mainSlot = parsed?.optString("mainSlot").orEmpty()
    return buildString {
        append("原厂字体扫描完成")
        if (slots >= 0) append(" · ").append(slots).append(" 个槽位")
        if (mainSlot.isNotBlank()) append(" · 主槽 ").append(mainSlot)
    }
}

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
    var stockScanBusy by remember { mutableStateOf(false) }
    var stockScanMessage by remember { mutableStateOf("") }
    var stockScanError by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

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

    HomeScreenCompact(
        style = style,
        state = state,
        actions = actions,
        trustContent = {
            if (state.moduleInstalled) {
                Column(Modifier.fillMaxWidth()) {
                    DeviceTrustChip(
                        style = style,
                        state = trustState,
                        onClick = { showTrustDetails = true },
                    )
                    Spacer(Modifier.height(7.dp))
                    OutlinedButton(
                        onClick = {
                            if (stockScanBusy) return@OutlinedButton
                            stockScanBusy = true
                            stockScanMessage = "正在从原厂 lower / mirror 扫描字体槽位…"
                            stockScanError = false
                            scope.launch {
                                val result = RootShell.exec(STOCK_SCAN_COMMAND, timeoutMs = 180_000L)
                                stockScanMessage = stockScanResultMessage(result.stdout, result.stderr, result.code)
                                stockScanError = result.code != 0 || stockScanMessage.contains("失败") || stockScanMessage.contains("无法")
                                stockScanBusy = false
                                if (!stockScanError) {
                                    actions.refresh()
                                    trustRefreshGeneration += 1
                                }
                            }
                        },
                        enabled = !stockScanBusy && !state.taskRunning,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            if (stockScanBusy) "正在扫描原厂字体…" else "重新扫描原厂字体",
                            fontWeight = FontWeight.Bold,
                        )
                    }
                    if (stockScanMessage.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            stockScanMessage,
                            color = if (stockScanError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                        )
                    }
                }
            }
        },
    )

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
