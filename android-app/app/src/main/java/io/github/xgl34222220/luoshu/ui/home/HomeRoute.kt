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
import androidx.lifecycle.viewmodel.compose.viewModel
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
import io.github.xgl34222220.luoshu.ui.logs.DiagnosticExportDialog
import io.github.xgl34222220.luoshu.ui.logs.DiagnosticExportState
import io.github.xgl34222220.luoshu.ui.logs.exportSanitizedDiagnostic
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

private const val STOCK_SCAN_COMMAND =
    "sh /data/adb/modules/LuoShu/common/font_manager.sh action stock_scan"

// After a successful rescan drop only a failed cache marker (#199) so the next apply starts clean.
private const val CACHE_CLEAR_FAILED_COMMAND =
    "MODDIR=/data/adb/modules/LuoShu MODULE_DIR=/data/adb/modules/LuoShu " +
        "sh /data/adb/modules/LuoShu/common/device_font_cache.sh clear-failed"

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
    var deviceDetailsExpanded by remember { mutableStateOf(false) }
    var diagnosticState by remember { mutableStateOf(DiagnosticExportState()) }
    val scope = rememberCoroutineScope()
    val runStockScan: () -> Unit = scan@{
        if (stockScanBusy) return@scan
        stockScanBusy = true
        stockScanMessage = "正在扫描设备原厂字体…"
        stockScanError = false
        scope.launch {
            val result = RootShell.exec(STOCK_SCAN_COMMAND, timeoutMs = 180_000L)
            stockScanMessage = stockScanResultMessage(result.stdout, result.stderr, result.code)
            stockScanError = result.code != 0 || stockScanMessage.contains("失败") || stockScanMessage.contains("无法")
            if (!stockScanError) {
                RootShell.exec(CACHE_CLEAR_FAILED_COMMAND, timeoutMs = 12_000L)
            }
            stockScanBusy = false
            if (!stockScanError) {
                actions.refresh()
                trustRefreshGeneration += 1
            }
        }
    }
    val runDiagnosticExport: () -> Unit = export@{
        if (diagnosticState.busy) return@export
        diagnosticState = DiagnosticExportState(busy = true)
        scope.launch { diagnosticState = exportSanitizedDiagnostic() }
    }

    LaunchedEffect(
        state.moduleInstalled,
        state.rootGranted,
        state.loading,
        state.statusCached,
        deviceDetailsExpanded,
        showTrustDetails,
        showAcceptanceGuide,
        state.currentFont,
        state.rebootRequired,
        state.taskRunning,
        trustRefreshGeneration,
    ) {
        if (!state.moduleInstalled || !state.rootGranted || state.loading || state.statusCached) {
            trustState = DeviceTrustState(
                loading = state.loading,
                error = when {
                    !state.moduleInstalled -> "请先安装洛书模块"
                    !state.rootGranted -> "请先授予 Root 权限"
                    state.loading -> "正在核实模块状态"
                    else -> "等待读取设备当前状态"
                },
            )
            return@LaunchedEffect
        }

        // The collapsed home card needs no second Root request or polling worker.
        if (!deviceDetailsExpanded && !showTrustDetails && !showAcceptanceGuide) return@LaunchedEffect

        var latest = loadDeviceTrustState()
        trustState = latest
        var attempt = 0
        while (latest.level == DeviceTrustLevel.PENDING && attempt < 9 && !state.taskRunning && !state.rebootRequired) {
            delay(5_000L)
            latest = loadDeviceTrustState()
            trustState = latest
            attempt += 1
        }
    }

    val coverageModel: HyperOsCoverageModel = viewModel()
    val coverageReady = state.moduleInstalled && state.rootGranted && !state.loading && !state.statusCached
    LaunchedEffect(coverageReady) { if (coverageReady) coverageModel.load() }

    HomeScreenMiuix(
        style = style,
        state = state,
        actions = actions,
        onDeviceDetailsExpanded = { deviceDetailsExpanded = it },
        showHyperOsCoverage = coverageReady && coverageModel.status?.hyperOs == true,
        hyperOsCoverageContent = { HyperOsCoverageSection(coverageModel) },
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
                        onClick = runStockScan,
                        enabled = !stockScanBusy && !state.taskRunning && state.rootGranted &&
                            !state.loading && !state.statusCached,
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
                            fontSize = 12.sp,
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
            onRescan = {
                showTrustDetails = false
                runStockScan()
            },
            onExportDiagnostic = runDiagnosticExport,
            recoveryBusy = stockScanBusy || diagnosticState.busy || state.taskRunning,
        )
    }
    if (diagnosticState.resultVisible) {
        DiagnosticExportDialog(
            style = style,
            state = diagnosticState,
            onDismiss = { diagnosticState = DiagnosticExportState() },
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
