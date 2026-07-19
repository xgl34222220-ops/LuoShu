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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest

private const val APP_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"
private const val PREVIEW_CACHE_MAX_FILES = 6
private const val PREVIEW_CACHE_MAX_BYTES = 96L * 1024L * 1024L

internal data class WeightAxisInfo(
    val loading: Boolean = true,
    val hasWeight: Boolean = false,
    val min: Int = 100,
    val default: Int = 400,
    val max: Int = 900,
    val error: String = "",
)

private data class PreviewTypefaceState(
    val typeface: Typeface? = null,
    val source: String = "",
    val error: String = "",
)

@Composable
internal fun rememberWeightAxisInfo(font: FontItem?): WeightAxisInfo {
    val info by produceState(
        initialValue = WeightAxisInfo(loading = font?.variable == true),
        key1 = font?.id,
    ) {
        value = when {
            font == null -> WeightAxisInfo(loading = false, error = "未选择字体")
            !font.variable -> WeightAxisInfo(loading = false, hasWeight = false)
            else -> runCatching {
                val command = "sh ${RootShell.quote(APP_BRIDGE)} weight_axis ${RootShell.quote(font.id)}"
                val result = RootShell.exec(command, timeoutMs = 25_000L)
                if (result.code != 0) error(result.stderr.ifBlank { bridgeError(result.stdout, "字重轴读取失败") })
                val jsonLine = result.stdout.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
                    ?: error("未收到字重轴数据")
                val root = JSONObject(jsonLine.trim())
                if (root.optString("status") != "ok") error(root.optString("message", "字重轴读取失败"))
                val weight = root.optJSONObject("weight")
                if (!root.optBoolean("hasWeight", false) || weight == null) {
                    WeightAxisInfo(loading = false, hasWeight = false)
                } else {
                    val min = weight.optDouble("min", 100.0).toInt()
                    val max = weight.optDouble("max", 900.0).toInt()
                    val default = weight.optDouble("default", 400.0).toInt().coerceIn(min, max)
                    WeightAxisInfo(
                        loading = false,
                        hasWeight = true,
                        min = min,
                        default = default,
                        max = max,
                    )
                }
            }.getOrElse { error ->
                WeightAxisInfo(loading = false, hasWeight = false, error = error.message ?: "字重轴读取失败")
            }
        }
    }
    return info
}

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
    val errorColor = MaterialTheme.colorScheme.error.toArgb()
    val previewRevision = font?.let { "${it.id}|${it.size}|${it.date}" }
    val preview by produceState(initialValue = PreviewTypefaceState(), key1 = previewRevision) {
        value = withContext(Dispatchers.IO) {
            when {
                font == null -> PreviewTypefaceState(error = "未选择字体")
                !font.valid -> PreviewTypefaceState(error = font.error.ifBlank { "字体无效" })
                else -> runCatching {
                    val cacheDir = File(context.cacheDir, "native-font-preview").apply { mkdirs() }
                    val extension = font.format.lowercase().takeIf { it in setOf("ttf", "otf", "ttc") } ?: "ttf"
                    val revision = "${font.id}|${font.size}|${font.date}"
                    val target = File(cacheDir, "${stableKey(revision)}.$extension")
                    val command = "sh ${RootShell.quote(APP_BRIDGE)} preview_export " +
                        "${RootShell.quote(font.id)} ${RootShell.quote(target.absolutePath)}"
                    val result = RootShell.exec(command, timeoutMs = 25_000L)
                    val jsonLine = result.stdout.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
                    val root = jsonLine?.let { JSONObject(it.trim()) }
                    if (result.code != 0 || root?.optString("status") != "ok") {
                        error(root?.optString("message").orEmpty().ifBlank {
                            result.stderr.ifBlank { "预览字体导出失败" }
                        })
                    }
                    if (!target.isFile || target.length() == 0L) error("预览字体文件为空")
                    val loaded = Typeface.createFromFile(target)
                    target.setLastModified(System.currentTimeMillis())
                    trimPreviewCache(cacheDir, target)
                    PreviewTypefaceState(
                        typeface = loaded,
                        source = root?.optJSONObject("data")?.optString("source").orEmpty(),
                    )
                }.getOrElse { error ->
                    PreviewTypefaceState(error = error.message ?: "预览字体加载失败")
                }
            }
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
                setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, textSizeSp)
            }
        },
        update = { view ->
            val failed = preview.error.isNotBlank()
            view.text = if (failed) "预览失败 · ${preview.error}" else text
            view.typeface = preview.typeface ?: Typeface.DEFAULT
            view.gravity = gravity
            view.maxLines = maxLines
            view.setTextColor(if (failed) errorColor else textColor)
            view.setTextSize(
                android.util.TypedValue.COMPLEX_UNIT_SP,
                if (failed) minOf(textSizeSp, 12f) else textSizeSp,
            )
        },
    )
}

private fun bridgeError(raw: String, fallback: String): String {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") } ?: return fallback
    return runCatching { JSONObject(line.trim()).optString("message", fallback) }.getOrDefault(fallback)
}

private fun stableKey(value: String): String {
    val bytes = MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
    return bytes.take(12).joinToString("") { byte -> "%02x".format(byte) }
}

private fun trimPreviewCache(directory: File, keep: File) {
    val files = directory.listFiles()
        ?.filter { it.isFile }
        ?.sortedByDescending { it.lastModified() }
        .orEmpty()
    var keptFiles = 0
    var keptBytes = 0L
    files.forEach { file ->
        val required = file.absolutePath == keep.absolutePath
        val fits = keptFiles < PREVIEW_CACHE_MAX_FILES &&
            keptBytes + file.length() <= PREVIEW_CACHE_MAX_BYTES
        if (required || fits) {
            keptFiles += 1
            keptBytes += file.length()
        } else {
            file.delete()
        }
    }
}
