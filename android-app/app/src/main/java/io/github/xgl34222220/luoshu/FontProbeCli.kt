package io.github.xgl34222220.luoshu

import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Typeface
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Small app_process entry point used by the module after boot.
 *
 * Android devices may expose several generated 400-weight slots (global UI,
 * clock, OEM named families). The shell supplies one visible anchor; the probe
 * also inspects sibling and known partition font directories, then reports the
 * best Typeface.DEFAULT outline match instead of trusting the first slot.
 */
object FontProbeCli {
    private val samples = listOf("洛", "书", "中", "文", "你", "好", "A", "a", "1", "0", "，", "。")
    private val generatedRegular = Regex("^LuoShuSlot-.*-400\\.ttf$", RegexOption.IGNORE_CASE)
    private val knownFontDirectories = listOf(
        "/system/fonts",
        "/system/system/fonts",
        "/system_ext/fonts",
        "/system/system_ext/fonts",
        "/product/fonts",
        "/system/product/fonts",
        "/vendor/fonts",
        "/odm/fonts",
        "/my_product/fonts",
        "/oplus_product/fonts",
        "/mi_ext/fonts",
    )

    @JvmStatic
    fun main(args: Array<String>) {
        val result = runCatching {
            require(args.isNotEmpty()) { "缺少待验证字体路径" }
            val candidates = discoverCandidates(args)
                .map(::probe)
                .toList()
            require(candidates.isNotEmpty()) { "没有可读取的 400 字重验证字体" }
            val best = candidates.maxWithOrNull(
                compareBy<JSONObject> { item -> item.optDouble("ratio", 0.0) }
                    .thenBy { item -> item.optInt("comparable", 0) }
                    .thenBy { item -> -(item.optJSONArray("missingActual")?.length() ?: Int.MAX_VALUE) },
            ) ?: error("验证候选为空")
            best.put("candidates", candidates.size)
        }.getOrElse { error ->
            JSONObject()
                .put("status", "error")
                .put("message", error.message ?: error.javaClass.simpleName)
        }
        println(result.toString())
    }

    private fun discoverCandidates(args: Array<String>): Sequence<File> {
        val anchors = args.asSequence().map(::File).toList()
        val directories = buildList {
            addAll(knownFontDirectories.map(::File))
            anchors.mapNotNullTo(this) { file -> file.parentFile }
        }
        return sequence {
            yieldAll(anchors)
            directories.forEach { directory ->
                val siblings = directory.listFiles { file ->
                    file.isFile && generatedRegular.matches(file.name)
                }
                if (siblings != null) yieldAll(siblings.asSequence())
            }
        }
            .filter { file -> file.isFile && file.length() >= 4_096L }
            .distinctBy { file -> file.canonicalPath }
    }

    private fun probe(file: File): JSONObject {
        val expected = Typeface.Builder(file).build()
        val actual = Typeface.DEFAULT
        val mismatched = JSONArray()
        val missingActual = JSONArray()
        val missingExpected = JSONArray()
        var matched = 0
        var comparable = 0

        samples.forEach { sample ->
            val actualFingerprint = glyphFingerprint(actual, sample)
            val expectedFingerprint = glyphFingerprint(expected, sample)
            when {
                actualFingerprint == null -> missingActual.put(sample)
                expectedFingerprint == null -> missingExpected.put(sample)
                else -> {
                    comparable += 1
                    if (actualFingerprint == expectedFingerprint) {
                        matched += 1
                    } else {
                        mismatched.put(sample)
                    }
                }
            }
        }
        val ratio = if (comparable == 0) 0.0 else matched.toDouble() / comparable.toDouble()
        return JSONObject()
            .put("status", "ok")
            .put("path", file.path)
            .put("matched", matched)
            .put("comparable", comparable)
            .put("total", samples.size)
            .put("ratio", ratio)
            .put("mismatched", mismatched)
            .put("missingActual", missingActual)
            .put("missingExpected", missingExpected)
    }

    private fun glyphFingerprint(typeface: Typeface, text: String): String? {
        val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.SUBPIXEL_TEXT_FLAG).apply {
            this.typeface = typeface
            textSize = 256f
            isLinearText = true
            hinting = Paint.HINTING_OFF
        }
        if (!paint.hasGlyph(text)) return null
        val path = Path()
        paint.getTextPath(text, 0, text.length, 0f, 0f, path)
        if (path.isEmpty) return null
        val bounds = RectF()
        path.computeBounds(bounds, true)
        if (bounds.width() <= 0f || bounds.height() <= 0f) return null
        val points = path.approximate(0.25f)
        if (points.size < 6) return null

        val normalized = StringBuilder(points.size * 4)
        var index = 0
        while (index + 2 < points.size) {
            val fraction = (points[index] * 1_000f).roundToInt()
            val x = (((points[index + 1] - bounds.left) / bounds.width()) * 4_096f).roundToInt()
            val y = (((points[index + 2] - bounds.top) / bounds.height()) * 4_096f).roundToInt()
            normalized.append(fraction).append(':').append(x).append(':').append(y).append(';')
            index += 3
        }
        val digest = MessageDigest.getInstance("SHA-256").digest(normalized.toString().toByteArray())
        return digest.joinToString("") { byte -> String.format(Locale.US, "%02x", byte.toInt() and 0xff) }
    }
}
