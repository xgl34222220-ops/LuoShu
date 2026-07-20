package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Cancel
import androidx.compose.material.icons.rounded.DeleteSweep
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Replay
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.NativeImportPhase
import io.github.xgl34222220.luoshu.NativeImportState
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun ImportTaskControls(
    style: UiStyle,
    state: NativeImportState,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (state.taskId.isBlank() || state.phase == NativeImportPhase.IDLE) return

    val tokens = LocalMiuixTokens.current
    val shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 30.dp else 24.dp)
    val container = if (style == UiStyle.MIUIX) {
        tokens.elevatedCardBackground
    } else {
        MaterialTheme.colorScheme.surfaceContainerHigh
    }

    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = shape,
        color = container.copy(alpha = .98f),
        shadowElevation = 18.dp,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .5f)),
    ) {
        Column(Modifier.padding(horizontal = 15.dp, vertical = 13.dp)) {
            Text(
                state.title,
                color = if (style == UiStyle.MIUIX) tokens.textPrimary else MaterialTheme.colorScheme.onSurface,
                fontSize = 15.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                state.message,
                color = if (style == UiStyle.MIUIX) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 10.sp,
                maxLines = 2,
            )
            if (state.busy || state.paused) {
                Spacer(Modifier.height(9.dp))
                LinearProgressIndicator(
                    progress = { state.progress.coerceIn(0, 100) / 100f },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                )
            }
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (state.canPause) {
                    FilledTonalButton(onClick = onPause) {
                        Icon(Icons.Rounded.Pause, contentDescription = null)
                        Text("暂停", modifier = Modifier.padding(start = 6.dp))
                    }
                }
                if (state.canResume) {
                    Button(onClick = onResume) {
                        Icon(Icons.Rounded.PlayArrow, contentDescription = null)
                        Text("继续", modifier = Modifier.padding(start = 6.dp))
                    }
                }
                if (state.canCancel) {
                    OutlinedButton(onClick = onCancel) {
                        Icon(Icons.Rounded.Cancel, contentDescription = null)
                        Text("取消", modifier = Modifier.padding(start = 6.dp))
                    }
                }
                if (state.canRetryFailed) {
                    FilledTonalButton(onClick = onRetry) {
                        Icon(Icons.Rounded.Replay, contentDescription = null)
                        Text("重试失败项", modifier = Modifier.padding(start = 6.dp))
                    }
                }
                if (state.canClear) {
                    OutlinedButton(onClick = onClear) {
                        Icon(Icons.Rounded.DeleteSweep, contentDescription = null)
                        Text("清除记录", modifier = Modifier.padding(start = 6.dp))
                    }
                }
            }
        }
    }
}
