package io.github.xgl34222220.luoshu.ui.library

import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.BuildConfig
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import java.io.File
import java.security.MessageDigest
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val FONT_ARCHIVE_BRIDGE = "/data/adb/modules/LuoShu/common/font_archive_export.sh"
private const val FONT_ARCHIVE_SCHEMA = 1
private const val FONT_ARCHIVE_TYPE = "luoshu-font-archive"
private const val FONT_ARCHIVE_MAX_FAMILIES = 32
private const val FONT_ARCHIVE_MAX_BYTES = 1_610_612_736L

@Immutable
internal data class FontArchiveFileRecord(
    val familyId: String,
    val familyName: String,
    val archivePath: String,
    val bytes: Long,
    val sha256: String,
)

internal fun safeFontArchiveSegment(value: String): String {
    val normalized = value.trim()
        .replace(Regex("[\\\\/:*?\"<>|\\p{Cntrl}]+"), "-")
        .replace(Regex("\\s+"), " ")
        .trim(' ', '.', '-')
    return normalized.take(80).ifBlank { "font" }
}

internal fun selectFontArchiveFamilies(
    fonts: List<FontItem>,
    selectedIds: Set<String>,
): List<FontItem> {
    require(selectedIds.isNotEmpty()) { "请至少选择一个字体 Family" }
    require(selectedIds.size <= FONT_ARCHIVE_MAX_FAMILIES) { "单次最多导出 32 个 Family" }
    val selected = fonts.filter { it.id in selectedIds }
    require(selected.size == selectedIds.size) { "选择中包含已不存在的 Family" }
    require(selected.all { it.valid }) { "无效字体不能进入归档" }
    return selected.sortedWith(compareBy<FontItem> { it.name.lowercase() }.thenBy { it.id })
}

internal fun buildFontArchiveManifest(
    records: List<FontArchiveFileRecord>,
    appVersion: String,
    createdAt: String,
): String {
    val grouped = records.groupBy { it.familyId }
    val families = JSONArray().apply {
        grouped.toSortedMap().forEach { (familyId, files) ->
            val first = files.first()
            put(
                JSONObject()
                    .put("id", familyId)
                    .put("name", first.familyName)
                    .put(
                        "files",
                        JSONArray().apply {
                            files.sortedBy { it.archivePath }.forEach { file ->
                                put(
                                    JSONObject()
                                        .put("path", file.archivePath)
                                        .put("bytes", file.bytes)
                                        .put("sha256", file.sha256),
                                )
                            }
                        },
                    ),
            )
        }
    }
    return JSONObject()
        .put("schema", FONT_ARCHIVE_SCHEMA)
        .put("type", FONT_ARCHIVE_TYPE)
        .put("appVersion", appVersion)
        .put("createdAt", createdAt)
        .put("includesFontFiles", true)
        .put("familyCount", grouped.size)
        .put("fileCount", records.size)
        .put("totalBytes", records.sumOf { it.bytes })
        .put("families", families)
        .put("note", "归档仅包含用户字体库中的字体文件与 SHA-256 校验清单，不包含设备原厂字体或私人路径。")
        .toString(2)
}

@Composable
internal fun FontArchiveExportTool(
    style: UiStyle,
    fonts: List<FontItem>,
    collections: FontLibraryCollections,
    enabled: Boolean,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val validFonts = remember(fonts) { fonts.filter { it.valid } }
    var showDialog by remember { mutableStateOf(false) }
    var selectedIds by remember { mutableStateOf(emptySet<String>()) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/zip"),
    ) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        val selected = runCatching { selectFontArchiveFamilies(validFonts, selectedIds) }
            .getOrElse {
                errorMessage = it.message ?: "字体选择无效"
                return@rememberLauncherForActivityResult
            }
        scope.launch {
            busy = true
            status = ""
            errorMessage = ""
            val result = runCatching { exportFontArchive(context, uri, selected) }
            busy = false
            if (result.isSuccess) {
                status = result.getOrThrow()
            } else {
                errorMessage = result.exceptionOrNull()?.message ?: "字体归档导出失败"
            }
        }
    }

    Surface(
        onClick = {
            val favoriteDefaults = collections.favoriteIds.intersect(validFonts.map { it.id }.toSet())
                .take(FONT_ARCHIVE_MAX_FAMILIES)
                .toSet()
            selectedIds = favoriteDefaults.ifEmpty { validFonts.firstOrNull()?.let { setOf(it.id) }.orEmpty() }
            status = ""
            errorMessage = ""
            showDialog = true
        },
        enabled = enabled && validFonts.isNotEmpty(),
        modifier = modifier,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 19.dp),
        color = MaterialTheme.colorScheme.secondaryContainer,
        contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.FileDownload, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.size(8.dp))
            Column(Modifier.weight(1f)) {
                Text("字体文件归档", fontSize = 11.sp, fontWeight = FontWeight.Black)
                Text(
                    "真实文件 · SHA-256 清单 · 最多 32 个 Family",
                    fontSize = 9.sp,
                    color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = .72f),
                )
            }
        }
    }

    if (showDialog) {
        AlertDialog(
            onDismissRequest = { if (!busy) showDialog = false },
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            icon = {
                if (busy) CircularProgressIndicator(Modifier.size(26.dp), strokeWidth = 2.dp)
                else Icon(Icons.Rounded.FileDownload, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            },
            title = { Text("导出字体文件归档", fontWeight = FontWeight.Black) },
            text = {
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text(
                        "归档会从洛书字体库只读复制真实 TTF、OTF、TTC 文件，并生成 SHA-256 manifest.json。不会导出设备原厂字体，也不会写入或修改字体库。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        OutlinedButton(
                            onClick = {
                                selectedIds = collections.favoriteIds
                                    .intersect(validFonts.map { it.id }.toSet())
                                    .take(FONT_ARCHIVE_MAX_FAMILIES)
                                    .toSet()
                            },
                            enabled = !busy,
                            modifier = Modifier.weight(1f),
                        ) { Text("收藏", fontSize = 10.sp) }
                        OutlinedButton(
                            onClick = { selectedIds = validFonts.take(FONT_ARCHIVE_MAX_FAMILIES).map { it.id }.toSet() },
                            enabled = !busy,
                            modifier = Modifier.weight(1f),
                        ) { Text("前 32 项", fontSize = 10.sp) }
                        OutlinedButton(
                            onClick = { selectedIds = emptySet() },
                            enabled = !busy,
                            modifier = Modifier.weight(1f),
                        ) { Text("清空", fontSize = 10.sp) }
                    }
                    Text(
                        "已选择 ${selectedIds.size}/$FONT_ARCHIVE_MAX_FAMILIES 个 Family",
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    LazyColumn(
                        modifier = Modifier.fillMaxWidth().heightIn(max = 330.dp),
                        verticalArrangement = Arrangement.spacedBy(5.dp),
                    ) {
                        items(validFonts, key = { it.id }) { font ->
                            val selected = font.id in selectedIds
                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(16.dp),
                                color = if (selected) MaterialTheme.colorScheme.primaryContainer.copy(alpha = .45f)
                                else MaterialTheme.colorScheme.surfaceContainerLow,
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 5.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Checkbox(
                                        checked = selected,
                                        enabled = !busy && (selected || selectedIds.size < FONT_ARCHIVE_MAX_FAMILIES),
                                        onCheckedChange = { checked ->
                                            selectedIds = if (checked) selectedIds + font.id else selectedIds - font.id
                                        },
                                    )
                                    Column(Modifier.weight(1f)) {
                                        Text(font.name, fontSize = 11.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text(
                                            listOfNotNull(
                                                font.format.takeIf { it.isNotBlank() },
                                                font.weights.takeIf { it.isNotEmpty() }?.let { "${it.size} 档字重" },
                                                if (font.variable) "可变" else null,
                                            ).joinToString(" · ").ifBlank { "字体 Family" },
                                            fontSize = 9.sp,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    }
                                }
                            }
                        }
                    }
                    if (status.isNotBlank()) {
                        Surface(Modifier.fillMaxWidth(), RoundedCornerShape(16.dp), MaterialTheme.colorScheme.primaryContainer) {
                            Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Rounded.CheckCircle, contentDescription = null, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.size(6.dp))
                                Text(status, fontSize = 10.sp)
                            }
                        }
                    }
                    if (errorMessage.isNotBlank()) {
                        Surface(Modifier.fillMaxWidth(), RoundedCornerShape(16.dp), MaterialTheme.colorScheme.errorContainer) {
                            Row(Modifier.padding(10.dp), verticalAlignment = Alignment.Top) {
                                Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.size(6.dp))
                                Text(errorMessage, fontSize = 10.sp, color = MaterialTheme.colorScheme.onErrorContainer)
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = { exportLauncher.launch(fontArchiveFileName()) },
                    enabled = !busy && selectedIds.isNotEmpty(),
                ) { Text(if (busy) "正在归档" else "导出 ZIP", fontWeight = FontWeight.Black) }
            },
            dismissButton = {
                TextButton(onClick = { showDialog = false }, enabled = !busy) { Text("关闭") }
            },
        )
    }
}

private suspend fun exportFontArchive(
    context: Context,
    outputUri: Uri,
    selected: List<FontItem>,
): String {
    val root = File(context.cacheDir, "font_archive/export-${UUID.randomUUID()}")
    return try {
        withContext(Dispatchers.IO) {
            root.mkdirs()
            require(root.isDirectory) { "无法创建字体归档缓存" }
        }
        val exported = mutableListOf<Pair<FontItem, List<File>>>()
        var totalBytes = 0L
        selected.forEachIndexed { index, font ->
            val familyDir = File(root, "family-${index + 1}")
            val shell = RootShell.exec(
                "sh ${RootShell.quote(FONT_ARCHIVE_BRIDGE)} ${RootShell.quote(font.id)} ${RootShell.quote(familyDir.absolutePath)}",
                timeoutMs = 180_000L,
            )
            if (shell.code != 0) error(shell.stderr.ifBlank { "${font.name} 导出失败" })
            val response = firstArchiveJson(shell.stdout)
            if (response.optString("status") != "ok") error(response.optString("message", "${font.name} 导出失败"))
            val files = withContext(Dispatchers.IO) {
                familyDir.listFiles()
                    .orEmpty()
                    .filter { it.isFile && !it.isDirectory && it.length() > 0L }
                    .sortedBy { it.name }
            }
            require(files.isNotEmpty()) { "${font.name} 没有可归档字体文件" }
            totalBytes += files.sumOf { it.length() }
            require(totalBytes <= FONT_ARCHIVE_MAX_BYTES) { "归档内容超过 1.5 GB 限制" }
            exported += font to files
        }

        val records = withContext(Dispatchers.IO) {
            buildList {
                exported.forEach { (font, files) ->
                    val familyFolder = safeFontArchiveSegment(font.name) + "-" + safeFontArchiveSegment(font.id).take(24)
                    files.forEachIndexed { index, file ->
                        val extension = file.extension.lowercase().takeIf { it in setOf("ttf", "otf", "ttc") } ?: "font"
                        val archivePath = "fonts/$familyFolder/font-${(index + 1).toString().padStart(3, '0')}.$extension"
                        add(
                            FontArchiveFileRecord(
                                familyId = font.id,
                                familyName = font.name,
                                archivePath = archivePath,
                                bytes = file.length(),
                                sha256 = sha256(file),
                            ),
                        )
                    }
                }
            }
        }
        val manifest = buildFontArchiveManifest(
            records = records,
            appVersion = BuildConfig.VERSION_NAME,
            createdAt = LocalDateTime.now().toString(),
        )
        withContext(Dispatchers.IO) {
            val output = context.contentResolver.openOutputStream(outputUri, "w") ?: error("无法打开目标归档文件")
            ZipOutputStream(output.buffered()).use { zip ->
                val recordByPath = records.associateBy { it.archivePath }
                exported.forEach { (font, files) ->
                    val familyFolder = safeFontArchiveSegment(font.name) + "-" + safeFontArchiveSegment(font.id).take(24)
                    files.forEachIndexed { index, file ->
                        val extension = file.extension.lowercase().takeIf { it in setOf("ttf", "otf", "ttc") } ?: "font"
                        val path = "fonts/$familyFolder/font-${(index + 1).toString().padStart(3, '0')}.$extension"
                        require(recordByPath[path] != null) { "归档清单与字体文件不一致" }
                        zip.putNextEntry(ZipEntry(path).apply { time = 0L })
                        file.inputStream().buffered().use { input -> input.copyTo(zip, 128 * 1024) }
                        zip.closeEntry()
                    }
                }
                zip.putNextEntry(ZipEntry("manifest.json").apply { time = 0L })
                zip.write(manifest.toByteArray(Charsets.UTF_8))
                zip.closeEntry()
            }
        }
        "已导出 ${selected.size} 个 Family、${records.size} 个字体文件（${formatArchiveBytes(records.sumOf { it.bytes })}）"
    } finally {
        withContext(Dispatchers.IO) { root.deleteRecursively() }
    }
}

private fun firstArchiveJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("模块没有返回字体归档结果")
    return JSONObject(line.trim())
}

private fun sha256(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().buffered().use { input ->
        val buffer = ByteArray(128 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            digest.update(buffer, 0, count)
        }
    }
    return digest.digest().joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
}

private fun formatArchiveBytes(bytes: Long): String = when {
    bytes < 1024L -> "$bytes B"
    bytes < 1024L * 1024L -> "%.1f KB".format(bytes / 1024.0)
    bytes < 1024L * 1024L * 1024L -> "%.1f MB".format(bytes / (1024.0 * 1024.0))
    else -> "%.2f GB".format(bytes / (1024.0 * 1024.0 * 1024.0))
}

private fun fontArchiveFileName(): String {
    val timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"))
    return "LuoShu-font-archive-$timestamp.zip"
}
