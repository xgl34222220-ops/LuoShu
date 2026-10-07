package io.github.xgl34222220.luoshu

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSmoothShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Cancel
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.PlayArrow
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
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens

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

    if (embedded) {
        val tokens = LocalMiuixTokens.current
        Surface(
            modifier = modifier.fillMaxWidth(),
            shape = LuoShuSmoothShape(28.dp),
            color = tokens.cardBackground,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .48f)),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FontMetadataInspector(
                    viewModel = viewModel,
                    style = style,
                )
                ImportActionButton(
                    style = style,
                    state = state,
                    expanded = true,
                    enabled = importEnabled,
                    onImport = onImport,
                    modifier = Modifier.weight(1f),
                    embedded = true,
                )
            }
        }
    } else {
        Row(
            modifier = modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ImportActionButton(
                style = style,
                state = state,
                expanded = expanded,
                enabled = importEnabled,
                onImport = onImport,
            )
        }
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
    modifier: Modifier = Modifier,
    embedded: Boolean = false,
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
    val targetHeight = when {
        embedded && taskVisible -> 64.dp
        embedded -> 52.dp
        taskVisible -> 68.dp
        else -> 54.dp
    }
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
    val glassColor = if (embedded) {
        scheme.primary.copy(alpha = if (dark) .13f else .07f)
    } else {
        tokens.elevatedCardBackground.copy(alpha = if (dark) .94f else .96f)
    }
    val borderColor = scheme.outlineVariant.copy(alpha = .55f)
    val textColor = tokens.textPrimary

    val buttonModifier = if (embedded) {
        modifier.fillMaxWidth().height(height)
    } else {
        modifier.width(width).height(height)
    }
    Surface(
        onClick = onImport,
        enabled = enabled,
        modifier = buttonModifier,
        shape = LuoShuSmoothShape(if (embedded) 20.dp else 26.dp),
        color = glassColor,
        contentColor = scheme.primary,
        border = BorderStroke(1.dp, borderColor),
    ) {
        if (!expanded) {
            Box(contentAlignment = Alignment.Center) {
                LuoShuGlyph(
                    imageVector = Icons.Rounded.Add,
                    contentDescription = "导入字体",
                    size = LuoShuIconTokens.HeaderGlyph,
                )
            }
        } else {
            Column(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = if (taskVisible) 10.dp else 12.dp),
                horizontalAlignment = if (embedded) Alignment.CenterHorizontally else Alignment.End,
                verticalArrangement = Arrangement.Center,
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center,
                ) {
                    when {
                        state.busy -> CircularProgressIndicator(
                            modifier = Modifier.size(LuoShuIconTokens.CompactProgress),
                            strokeWidth = 2.dp,
                            color = scheme.primary,
                        )
                        state.paused -> LuoShuGlyph(
                            imageVector = Icons.Rounded.PlayArrow,
                            contentDescription = null,
                            size = LuoShuIconTokens.ToolGlyph,
                            opticalScale = .96f,
                        )
                        else -> LuoShuGlyph(
                            imageVector = Icons.Rounded.Add,
                            contentDescription = null,
                            size = LuoShuIconTokens.ToolGlyph,
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        when {
                            state.busy -> "导入 ${state.processed}/${state.total}"
                            state.paused -> "继续 ${state.processed}/${state.total}"
                            else -> "导入字体"
                        },
                        color = textColor,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
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

    val tokens = LocalMiuixTokens.current
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 660.dp),
            shape = LuoShuSmoothShape(32.dp),
            color = tokens.elevatedCardBackground,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f)),
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = LuoShuSmoothShape(18.dp),
                        color = accent.copy(alpha = .09f),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(icon, contentDescription = null, tint = accent)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Text(
                        state.title,
                        modifier = Modifier.weight(1f),
                        color = tokens.textPrimary,
                        fontSize = 22.sp,
                        lineHeight = 30.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Column(
                    modifier = Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(state.summary, color = tokens.textPrimary, fontSize = 14.sp, lineHeight = 22.sp)
                    Text(
                        "支持 TTF、OTF、TTC 与字体模块 ZIP。ZIP 只提取字体文件，不执行包内脚本。导入记录可在任务中心控制。",
                        color = tokens.textSecondary,
                        fontSize = 12.sp,
                        lineHeight = 18.sp,
                    )
                }
                Button(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    shape = LuoShuSmoothShape(18.dp),
                ) {
                    Text("完成", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}
