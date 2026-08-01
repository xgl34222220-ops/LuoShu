package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.overlay.OverlayDialog

@Composable
internal fun StudioRestoreNoticeMiuix(
    message: String,
    onDismiss: () -> Unit,
) {
    OverlayDialog(
        title = "备份恢复结果",
        summary = message,
        show = true,
        onDismissRequest = onDismiss,
    ) {
        Button(
            onClick = onDismiss,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("完成", fontWeight = FontWeight.Bold)
        }
    }
}
