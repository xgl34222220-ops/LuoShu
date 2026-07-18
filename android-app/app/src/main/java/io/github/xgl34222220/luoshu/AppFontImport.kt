package io.github.xgl34222220.luoshu

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

internal data class StagedFontImport(
    val file: File,
    val displayName: String,
)

private const val MAX_IMPORT_FILES = 20
private const val MAX_IMPORT_BYTES = 128L * 1024L * 1024L
private val supportedFontExtensions = setOf("ttf", "otf", "ttc")

internal suspend fun stageFontImports(context: Context, uris: List<Uri>): List<StagedFontImport> =
    withContext(Dispatchers.IO) {
        val selected = uris.distinctBy(Uri::toString)
        require(selected.isNotEmpty()) { "没有选择字体文件" }
        require(selected.size <= MAX_IMPORT_FILES) { "一次最多导入 $MAX_IMPORT_FILES 个字体文件" }

        val appContext = context.applicationContext
        val root = File(appContext.cacheDir, "font-import")
        root.deleteRecursively()
        check(root.mkdirs() || root.isDirectory) { "无法创建字体导入缓存" }

        try {
            selected.mapIndexed { index, uri ->
                val displayName = safeFontName(queryDisplayName(appContext, uri), index)
                val target = File(root, "$index-$displayName")
                val input = appContext.contentResolver.openInputStream(uri)
                    ?: error("无法读取 $displayName")
                var total = 0L
                input.use { source ->
                    target.outputStream().buffered().use { sink ->
                        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                        while (true) {
                            val read = source.read(buffer)
                            if (read < 0) break
                            total += read
                            require(total <= MAX_IMPORT_BYTES) { "$displayName 超过 128 MB，已拒绝导入" }
                            sink.write(buffer, 0, read)
                        }
                    }
                }
                require(total >= 12L) { "$displayName 不是有效字体文件" }
                StagedFontImport(target, displayName)
            }
        } catch (error: Throwable) {
            root.deleteRecursively()
            throw error
        }
    }

internal fun cleanupFontImports(imports: List<StagedFontImport>) {
    imports.firstOrNull()?.file?.parentFile?.deleteRecursively()
}

private fun queryDisplayName(context: Context, uri: Uri): String {
    context.contentResolver.query(
        uri,
        arrayOf(OpenableColumns.DISPLAY_NAME),
        null,
        null,
        null,
    )?.use { cursor ->
        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (index >= 0 && cursor.moveToFirst()) {
            cursor.getString(index)?.takeIf(String::isNotBlank)?.let { return it }
        }
    }
    return uri.lastPathSegment?.substringAfterLast('/')?.takeIf(String::isNotBlank)
        ?: "font.ttf"
}

private fun safeFontName(rawName: String, index: Int): String {
    val leaf = rawName.substringAfterLast('/').substringAfterLast('\\').trim()
    val extension = leaf.substringAfterLast('.', "").lowercase()
    require(extension in supportedFontExtensions) {
        "${leaf.ifBlank { "第 ${index + 1} 个文件" }} 不是 TTF、OTF 或 TTC 字体"
    }
    val stem = leaf.removeSuffix(".${leaf.substringAfterLast('.')}")
        .replace(Regex("[\\u0000-\\u001f\\\\/:*?\"<>|]"), "_")
        .trim(' ', '.')
        .take(160)
        .ifBlank { "font-${index + 1}" }
    return "$stem.$extension"
}
