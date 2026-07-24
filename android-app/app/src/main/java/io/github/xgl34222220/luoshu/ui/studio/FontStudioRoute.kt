package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.LuoShuViewModel
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun FontStudioRoute(
    style: UiStyle,
    state: FontStudioUiState,
    actions: FontStudioActions,
) {
    val context = LocalContext.current
    val studioViewModel: LuoShuViewModel = viewModel()
    val profileBridge = remember(context.applicationContext) {
        StudioProfileBridgeStore(context.applicationContext)
    }
    val latestActions by rememberUpdatedState(actions)
    var showCompositePreview by remember { mutableStateOf(false) }
    var showProfileTransfer by remember { mutableStateOf(false) }
    var showGlyphBrowser by remember { mutableStateOf(false) }
    var restoreNotice by remember { mutableStateOf("") }
    val stableActions = remember(studioViewModel) {
        FontStudioActions(
            refresh = { latestActions.refresh() },
            pickSlot = { latestActions.pickSlot(it) },
            updateFont = studioViewModel::updateMixFont,
            updateWeight = { slot, weight -> latestActions.updateWeight(slot, weight) },
            updateAxis = { slot, tag, value -> latestActions.updateAxis(slot, tag, value) },
            inspectCoverage = { latestActions.inspectCoverage(it) },
            startMix = { latestActions.startMix() },
            applyDirect = { latestActions.applyDirect(it) },
        )
    }

    LaunchedEffect(state.loading, state.fonts, state.slots) {
        if (!state.loading && state.slots.all { it.font != null }) {
            profileBridge.saveCurrent(encodeStudioProfile(state))
        }
        val pending = profileBridge.peekPending()
        if (pending.isBlank() || state.loading || state.fonts.isEmpty()) return@LaunchedEffect
        val parsed = parseStudioProfile(pending, state.fonts)
        profileBridge.clearPending()
        if (parsed.valid && parsed.profile != null) {
            applyStudioProfile(parsed.profile, stableActions)
            restoreNotice = buildString {
                append("备份中的组合方案已载入")
                if (parsed.warnings.isNotEmpty()) append("\n${parsed.warnings.joinToString("\n")}")
            }
        } else {
            restoreNotice = "组合方案未恢复：${parsed.errors.joinToString("；").ifBlank { "配置无效" }}"
        }
    }

    Column(Modifier.fillMaxSize()) {
        when (style) {
            UiStyle.MATERIAL -> FontStudioScreenMaterial(state, stableActions, Modifier.weight(1f))
            UiStyle.MIUIX -> FontStudioScreenMiuix(state, stableActions, Modifier.weight(1f))
        }
        StudioToolLauncherRow(
            style = style,
            enabled = state.hasFonts && !state.loading,
            onPreview = { showCompositePreview = true },
            onProfile = { showProfileTransfer = true },
            onGlyphs = { showGlyphBrowser = true },
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 10.dp),
        )
    }

    if (showCompositePreview) {
        StudioCompositePreviewDialog(
            style = style,
            state = state,
            onApplyPreset = { preset ->
                latestActions.updateWeight(MixSlot.Cjk, preset.weightFor(MixSlot.Cjk))
                latestActions.updateWeight(MixSlot.Latin, preset.weightFor(MixSlot.Latin))
                latestActions.updateWeight(MixSlot.Digit, preset.weightFor(MixSlot.Digit))
            },
            onDismiss = { showCompositePreview = false },
        )
    }
    if (showProfileTransfer) {
        StudioProfileTransferDialog(
            style = style,
            state = state,
            actions = stableActions,
            onDismiss = { showProfileTransfer = false },
        )
    }
    if (showGlyphBrowser) {
        StudioGlyphBrowserDialog(
            style = style,
            state = state,
            onDismiss = { showGlyphBrowser = false },
        )
    }
    if (restoreNotice.isNotBlank()) {
        AlertDialog(
            onDismissRequest = { restoreNotice = "" },
            title = { Text("备份恢复结果", fontWeight = FontWeight.Black) },
            text = { Text(restoreNotice) },
            confirmButton = { TextButton(onClick = { restoreNotice = "" }) { Text("完成") } },
        )
    }
}
