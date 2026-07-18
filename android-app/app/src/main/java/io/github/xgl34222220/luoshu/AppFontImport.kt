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
) {
    val isModulePackage: Boolean
        get() = displayName.substringAfterLast('.', "").equals("zip", ignoreCase = true)
}

private const val MAX_IMPORT_FILES = 20
private const val MAX_FONT_BYTES = 128L * 1024L * 1024L
private const val MAX_PACKAGE_BYTES = 256L * 1024L * 1024L
private val supportedImportExtensions = setOf("ttf", "otf", "ttc", "zip")

internal suspend fun stageFontImports(context: Context, uris: List<Uri>): List<StagedFontImport> =
    withContext(Dispatchers.IO) {
        val selected = uris.distinctBy(Uri::toString)
        require(selected.isNotEmpty()) { "没有选择字体或字体模块" }
        require(selected.size <= MAX_IMPORT_FILES) { "一次最多导入 $MAX_IMPORT_FILES 个文件" }

        val appContext = context.applicationContext
        val root = File(appContext.cacheDir, "font-import")
        root.deleteRecursively()
        check(root.mkdirs() || root.isDirectory) { "无法创建字体导入缓存" }

        try {
            selected.mapIndexed { index, uri ->
                val displayName = safeImportName(queryDisplayName(appContext, uri), index)
                val target = File(root, "$index-$displayName")
                val maxBytes = if (displayName.endsWith(".zip", ignoreCase = true)) MAX_PACKAGE_BYTES else MAX_FONT_BYTES
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
                            require(total <= maxBytes) {
                                if (displayName.endsWith(".zip", ignoreCase = true)) "$displayName 超过 256 MB，已拒绝导入"
                                else "$displayName 超过 128 MB，已拒绝导入"
                            }
                            sink.write(buffer, 0, read)
                        }
                    }
                }
                require(total >= 12L) { "$displayName 文件内容无效" }
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

private fun safeImportName(rawName: String, index: Int): String {
    val leaf = rawName.substringAfterLast('/').substringAfterLast('\\').trim()
    val extension = leaf.substringAfterLast('.', "").lowercase()
    require(extension in supportedImportExtensions) {
        "${leaf.ifBlank { "第 ${index + 1} 个文件" }} 不是字体文件或 Magisk 字体模块 ZIP"
    }
    val stem = leaf.removeSuffix(".${leaf.substringAfterLast('.')}")
        .replace(Regex("[\\u0000-\\u001f\\\\/:*?\"<>|]"), "_")
        .trim(' ', '.')
        .take(160)
        .ifBlank { if (extension == "zip") "font-module-${index + 1}" else "font-${index + 1}" }
    return "$stem.$extension"
}
