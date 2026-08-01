package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.NativeImportPhase
import io.github.xgl34222220.luoshu.NativeImportState
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.CircularProgressIndicator
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.LinearProgressIndicator
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.basic.TextButton
import top.yukonga.miuix.kmp.overlay.OverlayDialog
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun DiagnosticExportButtonMiuix(
    state: DiagnosticExportState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Button(
        onClick = onClick,
        enabled = !state.busy,
        modifier = modifier,
    ) {
        if (state.busy) {
            CircularProgressIndicator(
                progress = null,
                modifier = Modifier.size(21.dp),
            )
        } else {
            Icon(
                imageVector = Icons.Rounded.Description,
                contentDescription = null,
                modifier = Modifier.size(21.dp),
            )
        }
    }
}

@Composable
internal fun DiagnosticExportDialogMiuix(
    state: DiagnosticExportState,
    onDismiss: () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    val failed = state.error.isNotBlank()
    OverlayDialog(
        title = if (failed) "诊断报告生成失败" else "脱敏诊断报告已生成",
        summary = if (failed) {
            state.error
        } else {
            "报告只包含引擎状态和错误数量，不包含设备指纹、序列号、型号、字体名称、字体文件名或私人路径。"
        },
        show = true,
        onDismissRequest = onDismiss,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = if (failed) "生成失败" else "保存位置",
                    summary = if (failed) state.error else state.path,
                    startAction = {
                        Icon(
                            imageVector = if (failed) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                            contentDescription = null,
                            tint = if (failed) colors.error else colors.primary,
                            modifier = Modifier.padding(end = 16.dp).size(24.dp),
                        )
                    },
                )
            }
            Button(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("完成", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
internal fun ImportTaskControlsMiuix(
    state: NativeImportState,
    onPause: () -> Unit,
    onResume: () -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
    onClear: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (state.taskId.isBlank() || state.phase == NativeImportPhase.IDLE) return

    Card(modifier = modifier.fillMaxWidth()) {
        BasicComponent(
            title = state.title,
            summary = state.message,
            startAction = {
                if (state.busy) {
                    CircularProgressIndicator(
                        progress = null,
                        modifier = Modifier.padding(end = 16.dp).size(23.dp),
                    )
                } else {
                    Icon(
                        imageVector = if (state.failed.isNotEmpty()) Icons.Rounded.Warning else Icons.Rounded.Description,
                        contentDescription = null,
                        tint = if (state.failed.isNotEmpty()) MiuixTheme.colorScheme.error else MiuixTheme.colorScheme.primary,
                        modifier = Modifier.padding(end = 16.dp).size(23.dp),
                    )
                }
            },
        )
        if (state.busy || state.paused) {
            LinearProgressIndicator(
                progress = state.progress.coerceIn(0, 100) / 100f,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            )
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (state.canPause) {
                TextButton(text = "暂停", onClick = onPause)
            }
            if (state.canResume) {
                Button(onClick = onResume) { Text("继续", fontWeight = FontWeight.Bold) }
            }
            if (state.canCancel) {
                TextButton(text = "取消", onClick = onCancel)
            }
            if (state.canRetryFailed) {
                Button(onClick = onRetry) { Text("重试失败项", fontWeight = FontWeight.Bold) }
            }
            if (state.canClear) {
                TextButton(text = "清除记录", onClick = onClear)
            }
        }
    }
}
