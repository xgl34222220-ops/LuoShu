package io.github.xgl34222220.luoshu

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
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
internal fun NativeImportOverlayMaterial(
    viewModel: LuoShuViewModel,
    state: NativeImportState,
    expanded: Boolean,
    enabled: Boolean,
    embedded: Boolean,
    onImport: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (embedded) {
        Surface(
            modifier = modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            color = MaterialTheme.colorScheme.surfaceContainerLow,
            shadowElevation = 2.dp,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .5f)),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                FontMetadataInspector(
                    viewModel = viewModel,
                    style = io.github.xgl34222220.luoshu.ui.appearance.UiStyle.MATERIAL,
                )
                MaterialImportActionButton(
                    state = state,
                    expanded = true,
                    enabled = enabled,
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
            MaterialImportActionButton(
                state = state,
                expanded = expanded,
                enabled = enabled,
                onImport = onImport,
            )
        }
    }
}

@Composable
private fun MaterialImportActionButton(
    state: NativeImportState,
    expanded: Boolean,
    enabled: Boolean,
    onImport: () -> Unit,
    modifier: Modifier = Modifier,
    embedded: Boolean = false,
) {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.background.luminance() < .5f
    val taskVisible = state.busy || state.paused
    val targetWidth = when {
        !expanded -> 54.dp
        taskVisible -> 180.dp
        else -> 148.dp
    }
    val targetHeight = when {
        taskVisible -> 68.dp
        else -> 54.dp
    }
    val width by animateDpAsState(
        targetValue = targetWidth,
        animationSpec = spring(dampingRatio = .78f, stiffness = 430f),
        label = "materialImportWidth",
    )
    val height by animateDpAsState(
        targetValue = targetHeight,
        animationSpec = spring(dampingRatio = .82f, stiffness = 470f),
        label = "materialImportHeight",
    )
    val glassColor = when {
        embedded -> scheme.primaryContainer.copy(alpha = if (dark) .46f else .62f)
        dark -> scheme.surfaceContainerHigh.copy(alpha = .72f)
        else -> Color.White.copy(alpha = .70f)
    }
    val borderColor = if (dark) Color.White.copy(alpha = .14f) else Color.White.copy(alpha = .82f)
    val buttonModifier = if (embedded) {
        modifier.fillMaxWidth().height(height)
    } else {
        modifier.width(width).height(height)
    }

    Surface(
        onClick = onImport,
        enabled = enabled,
        modifier = buttonModifier,
        shape = if (embedded) RoundedCornerShape(20.dp) else CircleShape,
        color = glassColor,
        contentColor = scheme.primary,
        shadowElevation = if (embedded) 0.dp else 8.dp,
        border = BorderStroke(1.dp, if (embedded) scheme.primary.copy(alpha = .10f) else borderColor),
    ) {
        if (!expanded) {
            Box(contentAlignment = Alignment.Center) {
                Icon(Icons.Rounded.Add, contentDescription = "导入字体", modifier = Modifier.size(24.dp))
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
                            modifier = Modifier.size(19.dp),
                            strokeWidth = 2.dp,
                            color = scheme.primary,
                        )
                        state.paused -> Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                        else -> Icon(Icons.Rounded.Add, contentDescription = null)
                    }
                    Spacer(Modifier.width(8.dp))
                    Text(
                        text = when {
                            state.busy -> "导入 ${state.processed}/${state.total}"
                            state.paused -> "继续 ${state.processed}/${state.total}"
                            else -> "导入字体"
                        },
                        fontWeight = FontWeight.Black,
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
internal fun ImportResultDialogMaterial(
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

    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(icon, contentDescription = null, tint = accent) },
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
}
