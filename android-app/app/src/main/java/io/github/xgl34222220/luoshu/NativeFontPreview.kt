package io.github.xgl34222220.luoshu

import android.graphics.Typeface
import android.view.Gravity
import android.widget.TextView
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import java.io.File
import java.security.MessageDigest

private const val APP_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"

@Composable
internal fun NativeFontPreview(
    font: FontItem?,
    text: String,
    modifier: Modifier = Modifier,
    textSizeSp: Float = 25f,
    gravity: Int = Gravity.START or Gravity.CENTER_VERTICAL,
    maxLines: Int = 2,
) {
    val context = LocalContext.current.applicationContext
    val textColor = MaterialTheme.colorScheme.onSurface.toArgb()
    val typeface by produceState<Typeface?>(initialValue = null, key1 = font?.id) {
        value = font?.takeIf { it.valid }?.let { item ->
            runCatching {
                val cacheDir = File(context.cacheDir, "native-font-preview").apply { mkdirs() }
                val extension = item.format.lowercase().takeIf { it in setOf("ttf", "otf", "ttc") } ?: "ttf"
                val target = File(cacheDir, "${stableKey(item.id)}.$extension")
                if (!target.isFile || target.length() == 0L) {
                    val command = "sh ${RootShell.quote(APP_BRIDGE)} preview_export " +
                        "${RootShell.quote(item.id)} ${RootShell.quote(target.absolutePath)}"
                    val result = RootShell.exec(command, timeoutMs = 25_000L)
                    if (result.code != 0 || !target.isFile || target.length() == 0L) {
                        error(result.stderr.ifBlank { "预览字体导出失败" })
                    }
                }
                Typeface.createFromFile(target)
            }.getOrNull()
        }
    }

    AndroidView(
        modifier = modifier,
        factory = { viewContext ->
            TextView(viewContext).apply {
                includeFontPadding = false
                setSingleLine(false)
                this.gravity = gravity
                this.maxLines = maxLines
                setTextColor(textColor)
                setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, textSizeSp)
            }
        },
        update = { view ->
            view.text = text
            view.typeface = typeface ?: Typeface.DEFAULT
            view.gravity = gravity
            view.maxLines = maxLines
            view.setTextColor(textColor)
            view.setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, textSizeSp)
        },
    )
}

private fun stableKey(value: String): String {
    val bytes = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
    return bytes.take(12).joinToString("") { byte -> "%02x".format(byte) }
}
