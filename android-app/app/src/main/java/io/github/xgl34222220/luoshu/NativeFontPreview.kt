package io.github.xgl34222220.luoshu

import android.content.Context
import android.graphics.Typeface
import android.util.LruCache
import android.util.TypedValue
import android.view.Gravity
import android.widget.TextView
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.roundToInt
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val APP_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"
private const val PREVIEW_CACHE_MAX_FILES = 32
private const val PREVIEW_CACHE_MAX_BYTES = 256L * 1024L * 1024L
private const val PREVIEW_MEMORY_MAX_ENTRIES = 24
private const val PREVIEW_EXPORT_CONCURRENCY = 1
private const val PREVIEW_EXPORT_DEBOUNCE_MS = 140L

internal data class VariableAxisInfo(
    val tag: String,
    val min: Float,
    val default: Float,
    val max: Float,
)

internal data class WeightAxisInfo(
    val loading: Boolean = true,
    val hasWeight: Boolean = false,
    val min: Int = 100,
    val default: Int = 400,
    val max: Int = 900,
    val axes: List<VariableAxisInfo> = emptyList(),
    val error: String = "",
)

private data class PreviewTypefaceState(
    val typeface: Typeface? = null,
    val file: File? = null,
    val error: String = "",
)

private data class PreviewMemoryEntry(
    val typeface: Typeface,
    val file: File,
)

private class PreviewTextView(context: Context) : TextView(context) {
    private var lastText: String? = null
    private var lastTypeface: Typeface? = null
    private var lastGravity: Int = Int.MIN_VALUE
    private var lastMaxLines: Int = Int.MIN_VALUE
    private var lastColor: Int = Int.MIN_VALUE
    private var lastSizeSp: Float = Float.NaN

    init {
        includeFontPadding = false
        setSingleLine(false)
    }

    fun render(
        value: String,
        font: Typeface,
        gravityValue: Int,
        maxLinesValue: Int,
        color: Int,
        sizeSp: Float,
    ) {
        if (lastText != value) {
            text = value
            lastText = value
        }
        if (lastTypeface !== font) {
            typeface = font
            lastTypeface = font
        }
        if (lastGravity != gravityValue) {
            gravity = gravityValue
            lastGravity = gravityValue
        }
        if (lastMaxLines != maxLinesValue) {
            maxLines = maxLinesValue
            lastMaxLines = maxLinesValue
        }
        if (lastColor != color) {
            setTextColor(color)
            lastColor = color
        }
        if (lastSizeSp != sizeSp) {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
            lastSizeSp = sizeSp
        }
    }
}

private val previewMemoryCache = object : LruCache<String, PreviewMemoryEntry>(PREVIEW_MEMORY_MAX_ENTRIES) {}
private val previewLocks = ConcurrentHashMap<String, Mutex>()
private val previewExportSemaphore = Semaphore(PREVIEW_EXPORT_CONCURRENCY)
private val axisInfoCache = ConcurrentHashMap<String, WeightAxisInfo>()
private val axisInfoLocks = ConcurrentHashMap<String, Mutex>()

private fun previewMemoryGet(key: String): PreviewMemoryEntry? = synchronized(previewMemoryCache) {
    previewMemoryCache.get(key)
}

private fun previewMemoryPut(key: String, entry: PreviewMemoryEntry) = synchronized(previewMemoryCache) {
    previewMemoryCache.put(key, entry)
}

@Composable
internal fun rememberWeightAxisInfo(font: FontItem?): WeightAxisInfo {
    val cached = remember(font?.id) { font?.id?.let(axisInfoCache::get) }
    val info by produceState(
        initialValue = cached ?: WeightAxisInfo(loading = font?.variable == true),
        key1 = font?.id,
        key2 = font?.variable,
    ) {
        value = when {
            font == null -> WeightAxisInfo(loading = false, error = "未选择字体")
            !font.variable -> WeightAxisInfo(loading = false, hasWeight = false)
            cached != null -> cached
            else -> {
                val lock = axisInfoLocks.computeIfAbsent(font.id) { Mutex() }
                try {
                    lock.withLock {
                        axisInfoCache[font.id] ?: loadWeightAxisInfo(font).also { loaded ->
                            axisInfoCache[font.id] = loaded
                        }
                    }
                } finally {
                    axisInfoLocks.remove(font.id, lock)
                }
            }
        }
    }
    return info
}

private suspend fun loadWeightAxisInfo(font: FontItem): WeightAxisInfo = try {
    val command = "sh ${RootShell.quote(APP_BRIDGE)} weight_axis ${RootShell.quote(font.id)}"
    val result = RootShell.exec(command, timeoutMs = 25_000L)
    if (result.code != 0) {
        error(result.stderr.ifBlank { bridgeError(result.stdout, "字体轴读取失败") })
    }
    val jsonLine = result.stdout.lineSequence()
        .firstOrNull { it.trimStart().startsWith("{") }
        ?: error("未收到字体轴数据")
    val root = JSONObject(jsonLine.trim())
    if (root.optString("status") != "ok") {
        error(root.optString("message", "字体轴读取失败"))
    }
    val rawAxes = root.optJSONArray("axes")
    val axes = buildList {
        if (rawAxes != null) {
            for (index in 0 until rawAxes.length()) {
                val axis = rawAxes.optJSONObject(index) ?: continue
                val tag = axis.optString("tag").trim()
                val minimum = axis.optDouble("min", Double.NaN).toFloat()
                val maximum = axis.optDouble("max", Double.NaN).toFloat()
                val defaultValue = axis.optDouble("default", Double.NaN).toFloat()
                if (
                    tag.length == 4 &&
                    minimum.isFinite() &&
                    maximum.isFinite() &&
                    defaultValue.isFinite() &&
                    maximum >= minimum
                ) {
                    add(
                        VariableAxisInfo(
                            tag = tag,
                            min = minimum,
                            default = defaultValue.coerceIn(minimum, maximum),
                            max = maximum,
                        ),
                    )
                }
            }
        }
    }
    val weight = axes.firstOrNull { it.tag == "wght" }
    if (weight == null) {
        WeightAxisInfo(loading = false, hasWeight = false, axes = axes)
    } else {
        WeightAxisInfo(
            loading = false,
            hasWeight = true,
            min = weight.min.roundToInt(),
            default = weight.default.roundToInt(),
            max = weight.max.roundToInt(),
            axes = axes,
        )
    }
} catch (cancelled: CancellationException) {
    throw cancelled
} catch (error: Throwable) {
    WeightAxisInfo(
        loading = false,
        hasWeight = false,
        error = error.message ?: "字体轴读取失败",
    )
}

@Composable
internal fun NativeFontPreview(
    font: FontItem?,
    text: String,
    axes: Map<String, Float> = emptyMap(),
    modifier: Modifier = Modifier,
    textSizeSp: Float = 25f,
    gravity: Int = Gravity.START or Gravity.CENTER_VERTICAL,
    maxLines: Int = 2,
) {
    val context = LocalContext.current.applicationContext
    val textColor = MaterialTheme.colorScheme.onSurface.toArgb()
    val errorColor = MaterialTheme.colorScheme.error.toArgb()
    val cleanAxes = remember(axes) { normalizePreviewAxes(axes) }
    val axisKey = remember(cleanAxes) {
        cleanAxes.entries
            .sortedBy { it.key }
            .joinToString(",") { "${it.key}=${formatAxisValue(it.value)}" }
    }
    val requestedWeight = remember(cleanAxes) {
        (cleanAxes["wght"] ?: 400f).roundToInt().coerceIn(1, 1000)
    }
    val sourceRevision = remember(font, requestedWeight) {
        font?.let {
            val staticRevision = if (it.variable) "" else "|wght=$requestedWeight"
            "${it.id}|${it.size}|${it.date}$staticRevision"
        }
    }
    val extension = remember(font?.format) {
        font?.format?.lowercase()
            ?.takeIf { it in setOf("ttf", "otf", "ttc") }
            ?: "ttf"
    }
    val cacheDir = remember(context.cacheDir) {
        File(context.cacheDir, "native-font-preview").apply { mkdirs() }
    }
    val target = remember(sourceRevision, extension) {
        sourceRevision?.let { File(cacheDir, "${stableKey(it)}.$extension") }
    }
    val memoryEntry = remember(sourceRevision) { sourceRevision?.let(::previewMemoryGet) }
    val previewKey = remember(sourceRevision, font?.valid, font?.error) {
        "${sourceRevision.orEmpty()}|${font?.valid}|${font?.error.orEmpty()}"
    }

    val preview by produceState(
        initialValue = memoryEntry?.let { PreviewTypefaceState(it.typeface, it.file) }
            ?: PreviewTypefaceState(),
        key1 = previewKey,
    ) {
        // 快速滚动时先等待一小段时间；离开可视区的卡片会被 Compose 取消，
        // 避免为一闪而过的几十个字体启动 Root 导出和 Typeface 解析。
        if (memoryEntry == null && (target == null || !target.isFile || target.length() == 0L)) {
            delay(PREVIEW_EXPORT_DEBOUNCE_MS)
        }
        value = withContext(Dispatchers.IO) {
            when {
                font == null -> PreviewTypefaceState(error = "未选择字体")
                !font.valid -> PreviewTypefaceState(error = font.error.ifBlank { "字体无效" })
                sourceRevision == null || target == null -> PreviewTypefaceState(error = "字体索引无效")
                else -> {
                    val lock = previewLocks.computeIfAbsent(sourceRevision) { Mutex() }
                    try {
                        lock.withLock {
                            previewMemoryGet(sourceRevision)?.let { cachedEntry ->
                                return@withLock PreviewTypefaceState(cachedEntry.typeface, cachedEntry.file)
                            }
                            previewExportSemaphore.withPermit {
                                try {
                                    var exported = false
                                    if (!target.isFile || target.length() == 0L) {
                                        val command = "sh ${RootShell.quote(APP_BRIDGE)} preview_export " +
                                            "${RootShell.quote(font.id)} ${RootShell.quote(target.absolutePath)} $requestedWeight"
                                        val result = RootShell.exec(command, timeoutMs = 25_000L)
                                        val jsonLine = result.stdout.lineSequence()
                                            .firstOrNull { it.trimStart().startsWith("{") }
                                        val root = jsonLine?.let { JSONObject(it.trim()) }
                                        if (result.code != 0 || root?.optString("status") != "ok") {
                                            error(
                                                root?.optString("message").orEmpty().ifBlank {
                                                    result.stderr.ifBlank { "预览字体导出失败" }
                                                },
                                            )
                                        }
                                        if (!target.isFile || target.length() == 0L) {
                                            error("预览字体文件为空")
                                        }
                                        exported = true
                                    }
                                    val loaded = Typeface.createFromFile(target)
                                    target.setLastModified(System.currentTimeMillis())
                                    if (exported) trimPreviewCache(cacheDir, target)
                                    previewMemoryPut(
                                        sourceRevision,
                                        PreviewMemoryEntry(typeface = loaded, file = target),
                                    )
                                    PreviewTypefaceState(typeface = loaded, file = target)
                                } catch (cancelled: CancellationException) {
                                    throw cancelled
                                } catch (error: Throwable) {
                                    PreviewTypefaceState(error = error.message ?: "预览字体加载失败")
                                }
                            }
                        }
                    } finally {
                        previewLocks.remove(sourceRevision, lock)
                    }
                }
            }
        }
    }

    val previewFile = preview.file
    val variationSettings = remember(axisKey) {
        cleanAxes.takeIf { it.isNotEmpty() }?.let(::toAndroidVariationSettings).orEmpty()
    }
    val variationResult = remember(previewFile?.absolutePath, variationSettings, font?.variable, preview.typeface) {
        if (font?.variable != true || previewFile == null || variationSettings.isEmpty()) {
            Result.success(preview.typeface)
        } else {
            runCatching {
                Typeface.Builder(previewFile)
                    .setFontVariationSettings(variationSettings)
                    .build()
            }
        }
    }
    val variationError = variationResult.exceptionOrNull()?.message.orEmpty()
    val renderedTypeface = variationResult.fold(
        onSuccess = { it },
        onFailure = { preview.typeface },
    ) ?: Typeface.DEFAULT
    val failure = preview.error.ifBlank { variationError }
    val failed = failure.isNotBlank()
    val renderedText = if (failed) "预览失败 · $failure" else text
    val renderedColor = if (failed) errorColor else textColor
    val renderedSize = if (failed) minOf(textSizeSp, 12f) else textSizeSp

    AndroidView(
        modifier = modifier,
        factory = { viewContext -> PreviewTextView(viewContext) },
        update = { view ->
            view.render(
                value = renderedText,
                font = renderedTypeface,
                gravityValue = gravity,
                maxLinesValue = maxLines,
                color = renderedColor,
                sizeSp = renderedSize,
            )
        },
    )
}

private fun normalizePreviewAxes(axes: Map<String, Float>): Map<String, Float> =
    axes.filter { (tag, value) -> tag.length == 4 && value.isFinite() }

private fun toAndroidVariationSettings(axes: Map<String, Float>): String = axes.entries
    .sortedBy { it.key }
    .joinToString(", ") { (tag, value) -> "'$tag' ${formatAxisValue(value)}" }

private fun formatAxisValue(value: Float): String = if (value % 1f == 0f) {
    value.roundToInt().toString()
} else {
    value.toString().trimEnd('0').trimEnd('.')
}

private fun bridgeError(raw: String, fallback: String): String {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: return fallback
    return runCatching { JSONObject(line.trim()).optString("message", fallback) }
        .getOrDefault(fallback)
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
