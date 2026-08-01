package io.github.xgl34222220.luoshu

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.CircularProgressIndicator
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.LinearProgressIndicator
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.overlay.OverlayDialog
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun NativeImportOverlayMiuix(
    state: NativeImportState,
    expanded: Boolean,
    enabled: Boolean,
    embedded: Boolean,
    onImport: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MiuixTheme.colorScheme
    val taskVisible = state.busy || state.paused
    val title = when {
        state.busy -> "正在导入字体"
        state.paused -> "字体导入已暂停"
        else -> "导入字体"
    }
    val summary = when {
        state.busy -> "已处理 ${state.processed}/${state.total} · ${state.progress}%"
        state.paused -> "已处理 ${state.processed}/${state.total}，点击继续"
        else -> "支持 TTF、OTF、TTC 与字体模块 ZIP"
    }

    if (!embedded && !expanded) {
        Row(
            modifier = modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
        ) {
            Button(
                onClick = onImport,
                enabled = enabled,
            ) {
                Icon(
                    imageVector = Icons.Rounded.Add,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                )
                Text("导入", modifier = Modifier.padding(start = 7.dp))
            }
        }
        return
    }

    Card(modifier = modifier.fillMaxWidth()) {
        BasicComponent(
            title = title,
            summary = summary,
            startAction = {
                if (state.busy) {
                    CircularProgressIndicator(
                        progress = null,
                        modifier = Modifier.padding(end = 16.dp).size(24.dp),
                    )
                } else {
                    Icon(
                        imageVector = if (state.paused) Icons.Rounded.PlayArrow else Icons.Rounded.Add,
                        contentDescription = null,
                        tint = colors.primary,
                        modifier = Modifier.padding(end = 16.dp).size(24.dp),
                    )
                }
            },
        )
        if (taskVisible) {
            LinearProgressIndicator(
                progress = state.progress.coerceIn(0, 100) / 100f,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            Spacer(Modifier.size(12.dp))
        }
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 16.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "ZIP 只安全提取字体，不执行包内脚本",
                modifier = Modifier.weight(1f),
                color = colors.onSurfaceSecondary,
            )
            Spacer(Modifier.width(12.dp))
            Button(
                onClick = onImport,
                enabled = enabled,
            ) {
                Icon(
                    imageVector = if (state.paused) Icons.Rounded.PlayArrow else Icons.Rounded.Add,
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                )
                Text(
                    text = if (state.paused) "继续" else "选择文件",
                    modifier = Modifier.padding(start = 7.dp),
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}

@Composable
internal fun ImportResultDialogMiuix(
    state: NativeImportState,
    onDismiss: () -> Unit,
) {
    val failed = state.failed.isNotEmpty()
    val icon = if (failed) Icons.Rounded.Error else Icons.Rounded.CheckCircle
    val colors = MiuixTheme.colorScheme

    OverlayDialog(
        title = state.title,
        summary = state.summary,
        show = true,
        onDismissRequest = onDismiss,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = if (failed) colors.error else colors.primary,
                    modifier = Modifier.size(24.dp),
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    text = "ZIP 仅安全提取字体，不执行包内脚本。导入记录可在任务中心控制。",
                    color = colors.onSurfaceSecondary,
                    modifier = Modifier.weight(1f),
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
