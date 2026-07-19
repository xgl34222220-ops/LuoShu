package io.github.xgl34222220.luoshu

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Cancel
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
) {
    val importViewModel: NativeImportViewModel = androidx.lifecycle.viewmodel.compose.viewModel()
    val state = importViewModel.state

    LaunchedEffect(state.refreshToken) {
        if (state.refreshToken > 0L) viewModel.refreshFonts(force = true)
    }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        importViewModel.startImport(uris)
    }

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.End,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        FontMetadataInspector(
            viewModel = viewModel,
            style = style,
        )
        ImportActionButton(
            style = style,
            state = state,
            enabled = viewModel.snapshot.installed &&
                !viewModel.operationBusy &&
                !viewModel.mixState.busy &&
                (!state.busy || state.paused),
            onImport = {
                if (state.paused) {
                    importViewModel.resumeImport()
                } else {
                    launcher.launch(arrayOf("*/*"))
                }
            },
        )
    }

    if (state.resultVisible) {
        ImportResultDialog(
            style = style,
            state = state,
            onDismiss = importViewModel::dismissResult,
        )
    }
}

@Composable
private fun ImportActionButton(
    style: UiStyle,
    state: NativeImportState,
    enabled: Boolean,
    onImport: () -> Unit,
) {
    Surface(
        onClick = onImport,
        enabled = enabled,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 24.dp else 22.dp),
        color = MaterialTheme.colorScheme.primary,
        contentColor = MaterialTheme.colorScheme.onPrimary,
        shadowElevation = if (style == UiStyle.MIUIX) 18.dp else 14.dp,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .10f)),
    ) {
        Column(
            modifier = Modifier.padding(
                horizontal = if (style == UiStyle.MIUIX) 19.dp else 18.dp,
                vertical = if (style == UiStyle.MIUIX) 14.dp else 13.dp,
            ),
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                when {
                    state.busy -> CircularProgressIndicator(
                        modifier = Modifier.size(19.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                    state.paused -> Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                    else -> Icon(Icons.Rounded.Add, contentDescription = null)
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    when {
                        state.busy -> "导入 ${state.processed}/${state.total}"
                        state.paused -> "继续 ${state.processed}/${state.total}"
                        else -> "导入字体"
                    },
                    fontWeight = FontWeight.Black,
                )
            }
            if (state.busy || state.paused) {
                LinearProgressIndicator(
                    progress = { state.progress / 100f },
                    modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.onPrimary,
                    trackColor = MaterialTheme.colorScheme.onPrimary.copy(alpha = .24f),
                )
            }
        }
    }
}

@Composable
private fun ImportResultDialog(
    style: UiStyle,
    state: NativeImportState,
    onDismiss: () -> Unit,
) {
    val failed = state.failed.isNotEmpty()
    val cancelled = state.phase == NativeImportPhase.CANCELLED
    val icon = when {
        cancelled -> Icons.Rounded.Cancel
        failed -> Icons.Rounded.Error
        else -> Icons.Rounded.CheckCircle
    }
    val accent = when {
        failed -> MaterialTheme.colorScheme.error
        cancelled -> MaterialTheme.colorScheme.secondary
        else -> MaterialTheme.colorScheme.primary
    }

    if (style == UiStyle.MATERIAL) {
        AlertDialog(
            onDismissRequest = onDismiss,
            icon = {
                Icon(icon, contentDescription = null, tint = accent)
            },
            title = { Text(state.title, fontWeight = FontWeight.Black) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(state.summary)
                    Text(
                        "支持 TTF、OTF、TTC 与字体模块 ZIP。ZIP 只提取字体文件，不执行包内脚本。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            },
            confirmButton = { Button(onClick = onDismiss) { Text("完成") } },
            shape = MaterialTheme.shapes.extraLarge,
        )
    } else {
        val tokens = LocalMiuixTokens.current
        Dialog(onDismissRequest = onDismiss) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(38.dp),
                color = tokens.elevatedCardBackground,
                shadowElevation = 20.dp,
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(13.dp),
                ) {
                    Text(
                        "IMPORT RESULT",
                        color = accent,
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.sp,
                    )
                    Text(
                        state.title,
                        color = tokens.textPrimary,
                        fontSize = 25.sp,
                        lineHeight = 30.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(state.summary, color = tokens.textPrimary, lineHeight = 20.sp)
                    Text(
                        "ZIP 仅安全提取字体，不执行包内脚本。导入记录可在任务中心控制。",
                        color = tokens.textSecondary,
                        fontSize = 11.sp,
                    )
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
                        Button(onClick = onDismiss, shape = RoundedCornerShape(18.dp)) {
                            Text("完成", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}
