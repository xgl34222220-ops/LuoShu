package io.github.xgl34222220.luoshu

import android.content.Context
import android.util.AtomicFile
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

internal data class CachedFontIndex(
    val fingerprint: String,
    val currentFont: String,
    val fonts: List<FontItem>,
    val savedAt: Long,
)

internal class FontIndexStore(context: Context) {
    private val atomicFile = AtomicFile(
        File(context.applicationContext.filesDir, "font-index-v3.json"),
    )
    private val lock = Any()

    fun load(): CachedFontIndex? = synchronized(lock) {
        runCatching {
            if (!atomicFile.baseFile.isFile || atomicFile.baseFile.length() <= 0L) return@synchronized null
            val raw = atomicFile.openRead().bufferedReader().use { it.readText() }
            val root = JSONObject(raw)
            if (root.optInt("schema", 0) != SCHEMA_VERSION) return@synchronized null
            val array = root.optJSONArray("fonts") ?: return@synchronized null
            val fonts = parseFontItems(array)
            CachedFontIndex(
                fingerprint = root.optString("fingerprint", ""),
                currentFont = root.optString("current", "default"),
                fonts = fonts,
                savedAt = root.optLong("savedAt", 0L),
            )
        }.getOrNull()
    }

    fun save(index: CachedFontIndex) = synchronized(lock) {
        val root = JSONObject()
            .put("schema", SCHEMA_VERSION)
            .put("fingerprint", index.fingerprint)
            .put("current", index.currentFont)
            .put("savedAt", index.savedAt)
            .put(
                "fonts",
                JSONArray().apply {
                    index.fonts.forEach { font ->
                        put(
                            JSONObject()
                                .put("id", font.id)
                                .put("name", font.name)
                                .put("format", font.format)
                                .put("size", font.size)
                                .put("date", font.date)
                                .put("variable", font.variable)
                                .put("valid", font.valid)
                                .put("error", font.error)
                                .put("weights", JSONArray(font.weights))
                                .put("supportsCjk", font.supportsCjk)
                                .put("revision", font.revision),
                        )
                    }
                },
            )

        val output = atomicFile.startWrite()
        try {
            val bytes = root.toString().toByteArray(Charsets.UTF_8)
            output.write(bytes)
            output.flush()
            output.fd.sync()
            atomicFile.finishWrite(output)
        } catch (error: Throwable) {
            atomicFile.failWrite(output)
            throw error
        }
    }

    fun clear() = synchronized(lock) {
        atomicFile.delete()
    }

    private companion object {
        const val SCHEMA_VERSION = 3
    }
}
