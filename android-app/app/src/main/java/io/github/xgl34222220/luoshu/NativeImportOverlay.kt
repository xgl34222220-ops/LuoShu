package io.github.xgl34222220.luoshu

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import kotlinx.coroutines.delay

@Composable
internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
) {
    val importViewModel = rememberNativeImportViewModel()
    val state = importViewModel.state
    var expanded by remember { mutableStateOf(true) }

    LaunchedEffect(state.busy, state.paused, state.processed, state.total) {
        if (state.busy || state.paused) {
            expanded = true
        } else {
            expanded = true
            delay(2_400L)
            expanded = false
        }
    }

    LaunchedEffect(state.refreshToken) {
        if (state.refreshToken > 0L) viewModel.refreshFonts(force = true)
    }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        importViewModel.startImport(uris)
    }

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.End,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        FontMetadataInspector(
            viewModel = viewModel,
            style = style,
        )
        Spacer(Modifier.width(10.dp))
        ImportActionButton(
            style = style,
            state = state,
            expanded = expanded || state.busy || state.paused,
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
    expanded: Boolean,
    enabled: Boolean,
    onImport: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val dark = scheme.background.luminance() < .5f
    val taskVisible = state.busy || state.paused
    val targetWidth = when {
        !expanded -> 54.dp
        taskVisible -> 180.dp
        else -> 148.dp
    }
    val targetHeight = if (taskVisible) 68.dp else 54.dp
    val width by animateDpAsState(
        targetValue = targetWidth,
        animationSpec = spring(dampingRatio = .78f, stiffness = 430f),
        label = "nativeImportGlassWidth",
    )
    val height by animateDpAsState(
        targetValue = targetHeight,
        animationSpec = spring(dampingRatio = .82f, stiffness = 470f),
        label = "nativeImportGlassHeight",
    )
    val glassColor = when {
        style == UiStyle.MIUIX -> tokens.elevatedCardBackground.copy(alpha = if (dark) .76f else .72f)
        dark -> scheme.surfaceContainerHigh.copy(alpha = .72f)
        else -> Color.White.copy(alpha = .70f)
    }
    val borderColor = if (dark) Color.White.copy(alpha = .14f) else Color.White.copy(alpha = .82f)
    val textColor = if (style == UiStyle.MIUIX) tokens.textPrimary else scheme.onSurface

    Surface(
        onClick = onImport,
        enabled = enabled,
        modifier = Modifier.width(width).height(height),
        shape = CircleShape,
        color = glassColor,
        contentColor = scheme.primary,
        shadowElevation = if (style == UiStyle.MIUIX) 14.dp else 12.dp,
        border = BorderStroke(1.dp, borderColor),
    ) {
        if (!expanded) {
            Box(contentAlignment = Alignment.Center) {
                Icon(Icons.Rounded.Add, contentDescription = "导入字体", modifier = Modifier.size(24.dp))
            }
        } else {
            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = if (taskVisible) 10.dp else 12.dp),
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.Center,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    when {
                        state.busy -> CircularProgressIndicator(
                            modifier = Modifier.size(19.dp),
                            strokeWidth = 2.dp,
                            color = scheme.primary,
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
                        color = textColor,
                        fontWeight = FontWeight.Black,
                        fontSize = 15.sp,
                        maxLines = 1,
                        softWrap = false,
                    )
                }
                if (taskVisible) {
                    Spacer(Modifier.height(7.dp))
                    LinearProgressIndicator(
                        progress = { state.progress / 100f },
                        modifier = Modifier.fillMaxWidth(),
                        color = scheme.primary,
                        trackColor = scheme.primary.copy(alpha = .18f),
                    )
                }
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
