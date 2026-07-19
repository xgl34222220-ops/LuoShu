package io.github.xgl34222220.luoshu

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import java.io.File
import java.io.FileOutputStream
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val IMPORT_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"
private const val DETAILS_BRIDGE = "/data/adb/modules/LuoShu/common/font_details.sh"
private const val MAX_IMPORT_BYTES = 268_435_456L
private val ALLOWED_EXTENSIONS = setOf("ttf", "otf", "ttc", "zip")

private data class ImportSummary(
    val imported: Int,
    val duplicates: Int,
    val failed: List<String>,
) {
    val title: String get() = if (failed.isEmpty()) "导入完成" else "导入结果"
    val message: String
        get() = buildString {
            append("成功导入 ").append(imported).append(" 个文件")
            if (duplicates > 0) append("，跳过 ").append(duplicates).append(" 个重复字体")
            if (failed.isNotEmpty()) {
                append("\n\n失败：\n")
                failed.take(6).forEach { append("• ").append(it).append('\n') }
                if (failed.size > 6) append("其余 ").append(failed.size - 6).append(" 项请查看日志")
            }
        }.trimEnd()
}

private data class FontDetails(
    val title: String,
    val text: String,
)

@Composable
internal fun NativeImportOverlay(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var importBusy by remember { mutableStateOf(false) }
    var importSummary by remember { mutableStateOf<ImportSummary?>(null) }
    var showDetailsPicker by remember { mutableStateOf(false) }
    var detailsBusy by remember { mutableStateOf(false) }
    var details by remember { mutableStateOf<FontDetails?>(null) }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        if (uris.isEmpty() || importBusy) return@rememberLauncherForActivityResult
        importBusy = true
        scope.launch {
            importSummary = withContext(Dispatchers.IO) {
                importDocuments(context.applicationContext, uris)
            }
            importBusy = false
            viewModel.refreshFonts(force = true)
        }
    }

    ImportActions(
        style = style,
        importBusy = importBusy,
        detailsBusy = detailsBusy,
        detailsEnabled = viewModel.snapshot.installed && viewModel.fonts.isNotEmpty() && !detailsBusy,
        importEnabled = viewModel.snapshot.installed &&
            !importBusy &&
            !viewModel.operationBusy &&
            !viewModel.mixState.busy,
        onDetails = { showDetailsPicker = true },
        onImport = { launcher.launch(arrayOf("*/*")) },
        modifier = modifier,
    )

    importSummary?.let { result ->
        ImportResultDialog(style, result) { importSummary = null }
    }

    if (showDetailsPicker) {
        FontDetailsPickerDialog(
            style = style,
            fonts = viewModel.fonts,
            onDismiss = { showDetailsPicker = false },
            onChoose = { font ->
                showDetailsPicker = false
                detailsBusy = true
                scope.launch {
                    details = withContext(Dispatchers.IO) { loadFontDetails(font) }
                    detailsBusy = false
                }
            },
        )
    }

    if (detailsBusy) {
        AnalysisLoadingDialog(style)
    }

    details?.let { result ->
        FontDetailsDialog(style, result) { details = null }
    }
}

@Composable
private fun ImportActions(
    style: UiStyle,
    importBusy: Boolean,
    detailsBusy: Boolean,
    detailsEnabled: Boolean,
    importEnabled: Boolean,
    onDetails: () -> Unit,
    onImport: () -> Unit,
    modifier: Modifier,
) {
    val tokens = LocalMiuixTokens.current
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.End,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Surface(
            onClick = onDetails,
            enabled = detailsEnabled,
            modifier = Modifier.size(if (style == UiStyle.MIUIX) 54.dp else 52.dp),
            shape = if (style == UiStyle.MIUIX) RoundedCornerShape(19.dp) else CircleShape,
            color = if (style == UiStyle.MIUIX) {
                tokens.elevatedCardBackground
            } else {
                MaterialTheme.colorScheme.surface.copy(alpha = .96f)
            },
            contentColor = MaterialTheme.colorScheme.primary,
            shadowElevation = if (style == UiStyle.MIUIX) 16.dp else 12.dp,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .10f)),
        ) {
            Box(contentAlignment = Alignment.Center) {
                if (detailsBusy) {
                    CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Rounded.Info, contentDescription = "字体详情")
                }
            }
        }

        Surface(
            onClick = onImport,
            enabled = importEnabled,
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 24.dp else 22.dp),
            color = MaterialTheme.colorScheme.primary,
            contentColor = MaterialTheme.colorScheme.onPrimary,
            shadowElevation = if (style == UiStyle.MIUIX) 18.dp else 14.dp,
        ) {
            Row(
                modifier = Modifier.padding(
                    horizontal = if (style == UiStyle.MIUIX) 19.dp else 18.dp,
                    vertical = if (style == UiStyle.MIUIX) 16.dp else 15.dp,
                ),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (importBusy) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(19.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                } else {
                    Icon(Icons.Rounded.Add, contentDescription = null)
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    if (importBusy) "导入中" else "导入字体",
                    fontWeight = FontWeight.Black,
                )
            }
        }
    }
}

@Composable
private fun ImportResultDialog(
    style: UiStyle,
    result: ImportSummary,
    onDismiss: () -> Unit,
) {
    if (style == UiStyle.MATERIAL) {
        AlertDialog(
            onDismissRequest = onDismiss,
            icon = {
                Icon(
                    Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            },
            title = { Text(result.title, fontWeight = FontWeight.Black) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(result.message)
                    Text(
                        "支持 TTF、OTF、TTC 与字体模块 ZIP。ZIP 只提取字体文件，不执行包内脚本。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            },
            confirmButton = { Button(onClick = onDismiss) { Text("完成") } },
            shape = MaterialTheme.shapes.extraLarge,
        )
    } else {
        MiuixDialogFrame(
            eyebrow = "IMPORT RESULT",
            title = result.title,
            onDismiss = onDismiss,
        ) {
            Text(result.message, color = LocalMiuixTokens.current.textPrimary, lineHeight = 20.sp)
            Text(
                "ZIP 仅安全提取字体，不执行包内脚本。",
                color = LocalMiuixTokens.current.textSecondary,
                fontSize = 11.sp,
            )
            Button(
                onClick = onDismiss,
                modifier = Modifier.align(Alignment.End),
                shape = RoundedCornerShape(18.dp),
            ) { Text("完成", fontWeight = FontWeight.Bold) }
        }
    }
}

@Composable
private fun FontDetailsPickerDialog(
    style: UiStyle,
    fonts: List<FontItem>,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = remember(fonts, query) {
        val needle = query.trim()
        if (needle.isBlank()) fonts else fonts.filter { font ->
            font.name.contains(needle, ignoreCase = true) ||
                font.format.contains(needle, ignoreCase = true) ||
                font.weightLabel.contains(needle, ignoreCase = true)
        }
    }
    val body: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 20.dp else 16.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索字体") },
            )
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 420.dp),
                verticalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                items(filtered, key = { it.id }) { font ->
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(if (style == UiStyle.MIUIX) 24.dp else 18.dp))
                            .clickable { onChoose(font) },
                        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 24.dp else 18.dp),
                        color = if (style == UiStyle.MIUIX) {
                            LocalMiuixTokens.current.cardBackground
                        } else {
                            MaterialTheme.colorScheme.surfaceContainerLow
                        },
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Surface(
                                modifier = Modifier.size(44.dp),
                                shape = RoundedCornerShape(15.dp),
                                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                            ) {
                                Box(contentAlignment = Alignment.Center) {
                                    Text("Aa", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                                }
                            }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    font.name,
                                    fontWeight = FontWeight.Bold,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    listOf(font.format, font.size, font.weightLabel)
                                        .filter { it.isNotBlank() }
                                        .joinToString(" · "),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontSize = 10.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    if (style == UiStyle.MATERIAL) {
        AlertDialog(
            onDismissRequest = onDismiss,
            title = { Text("选择字体查看详情", fontWeight = FontWeight.Black) },
            text = body,
            confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
            shape = MaterialTheme.shapes.extraLarge,
        )
    } else {
        MiuixDialogFrame(
            eyebrow = "FONT DETAILS",
            title = "选择字体",
            onDismiss = onDismiss,
        ) {
            body()
            TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) {
                Text("关闭", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun AnalysisLoadingDialog(style: UiStyle) {
    if (style == UiStyle.MATERIAL) {
        AlertDialog(
            onDismissRequest = {},
            title = { Text("正在分析字体", fontWeight = FontWeight.Black) },
            text = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(12.dp))
                    Text("正在读取字体内部名称、字重、覆盖范围和可变轴…")
                }
            },
            confirmButton = {},
            shape = MaterialTheme.shapes.extraLarge,
        )
    } else {
        MiuixDialogFrame(
            eyebrow = "ANALYZING",
            title = "正在分析字体",
            onDismiss = {},
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(26.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(12.dp))
                Text(
                    "正在读取内部名称、字重、覆盖范围和可变轴…",
                    color = LocalMiuixTokens.current.textSecondary,
                )
            }
        }
    }
}

@Composable
private fun FontDetailsDialog(
    style: UiStyle,
    result: FontDetails,
    onDismiss: () -> Unit,
) {
    val body: @Composable () -> Unit = {
        SelectionContainer {
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 500.dp),
            ) {
                item {
                    Text(
                        result.text,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        lineHeight = 18.sp,
                    )
                }
            }
        }
    }
    if (style == UiStyle.MATERIAL) {
        AlertDialog(
            onDismissRequest = onDismiss,
            title = { Text(result.title, fontWeight = FontWeight.Black, maxLines = 2) },
            text = body,
            confirmButton = { Button(onClick = onDismiss) { Text("完成") } },
            shape = MaterialTheme.shapes.extraLarge,
        )
    } else {
        MiuixDialogFrame(
            eyebrow = "FONT METADATA",
            title = result.title,
            onDismiss = onDismiss,
        ) {
            body()
            Button(
                onClick = onDismiss,
                modifier = Modifier.align(Alignment.End),
                shape = RoundedCornerShape(18.dp),
            ) { Text("完成", fontWeight = FontWeight.Bold) }
        }
    }
}

@Composable
private fun MiuixDialogFrame(
    eyebrow: String,
    title: String,
    onDismiss: () -> Unit,
    content: @Composable Column.() -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(38.dp),
            color = tokens.elevatedCardBackground,
            shadowElevation = 20.dp,
        ) {
            Column(
                modifier = Modifier.padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(13.dp),
            ) {
                Text(
                    eyebrow,
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 2.sp,
                )
                Text(
                    title,
                    color = tokens.textPrimary,
                    fontSize = 25.sp,
                    lineHeight = 30.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                content()
            }
        }
    }
}

private suspend fun importDocuments(context: Context, uris: List<Uri>): ImportSummary {
    val cacheDir = File(context.cacheDir, "native_import")
    cacheDir.mkdirs()
    var imported = 0
    var duplicates = 0
    val failed = mutableListOf<String>()

    uris.take(32).forEachIndexed { index, uri ->
        var temp: File? = null
        val displayName = queryDisplayName(context, uri) ?: "font-${index + 1}"
        try {
            val extension = displayName.substringAfterLast('.', "").lowercase()
            require(extension in ALLOWED_EXTENSIONS) { "仅支持 TTF、OTF、TTC 和 ZIP" }
            temp = File(cacheDir, "${System.currentTimeMillis()}-${UUID.randomUUID()}.$extension")
            copyUriWithLimit(context, uri, temp)
            val result = RootShell.exec(
                "sh ${RootShell.quote(IMPORT_BRIDGE)} import_file " +
                    "${RootShell.quote(temp.absolutePath)} ${RootShell.quote(displayName)}",
                timeoutMs = if (extension == "zip") 180_000L else 60_000L,
            )
            if (result.code != 0) error(result.stderr.ifBlank { "Root 导入失败" })
            val root = firstJson(result.stdout)
            if (root.optString("status") != "ok") error(root.optString("message", "导入失败"))
            val duplicate = root.optJSONObject("data")?.optBoolean("duplicate", false) == true
            if (duplicate) duplicates += 1 else imported += 1
        } catch (error: Throwable) {
            failed += "$displayName：${error.message ?: "导入失败"}"
        } finally {
            temp?.delete()
        }
    }
    cacheDir.listFiles()?.filter { it.isFile }?.forEach { file ->
        if (System.currentTimeMillis() - file.lastModified() > 3_600_000L) file.delete()
    }
    return ImportSummary(imported = imported, duplicates = duplicates, failed = failed)
}

private suspend fun loadFontDetails(font: FontItem): FontDetails {
    return try {
        val result = RootShell.exec(
            "sh ${RootShell.quote(DETAILS_BRIDGE)} ${RootShell.quote(font.id)}",
            timeoutMs = 60_000L,
        )
        if (result.code != 0) error(result.stderr.ifBlank { "字体详情读取失败" })
        val root = firstJson(result.stdout)
        if (root.optString("status") != "ok") error(root.optString("message", "字体详情读取失败"))
        val data = root.getJSONObject("data")
        val faces = data.getJSONArray("faces")
        val title = faces.optJSONObject(0)?.optString("fullName", font.name).orEmpty().ifBlank { font.name }
        val text = buildString {
            append("文件：").append(data.optString("fileName")).append('\n')
            append("SHA-256：").append(data.optString("sha256")).append('\n')
            append("稳定文件 ID：").append(data.optString("fileUid")).append('\n')
            append("字体面数量：").append(data.optInt("faceCount", faces.length())).append('\n')
            append("文件大小：").append(formatBytes(data.optLong("bytes"))).append("\n\n")
            for (index in 0 until faces.length()) {
                val face = faces.optJSONObject(index) ?: continue
                val coverage = face.optJSONObject("coverage")
                val roles = coverage?.optJSONObject("roles")
                append("字体面 #").append(face.optInt("faceIndex", index)).append('\n')
                append("  名称：").append(face.optString("fullName", face.optString("family"))).append('\n')
                append("  Family：").append(face.optString("family")).append('\n')
                append("  Subfamily：").append(face.optString("subfamily")).append('\n')
                face.optString("postScriptName").takeIf { it.isNotBlank() }?.let {
                    append("  PostScript：").append(it).append('\n')
                }
                append("  稳定 ID：").append(face.optString("uid")).append('\n')
                append("  格式：").append(face.optString("format"))
                    .append(" · 字重 ").append(face.optInt("weight", 400))
                    .append(if (face.optBoolean("italic")) " · 斜体" else " · 正体")
                    .append('\n')
                append("  字形：").append(face.optInt("glyphs"))
                    .append(" · Unicode：").append(coverage?.optInt("codepoints") ?: 0)
                    .append(" · CJK：").append(coverage?.optInt("cjkCount") ?: 0)
                    .append('\n')
                append("  推荐角色：")
                val roleLabels = buildList {
                    if (roles?.optBoolean("cjk") == true) add("中文基底")
                    if (roles?.optBoolean("latin") == true) add("英文")
                    if (roles?.optBoolean("digit") == true) add("数字")
                }
                append(if (roleLabels.isEmpty()) "不满足完整角色门禁" else roleLabels.joinToString("、")).append('\n')
                val axes = face.optJSONArray("axes")
                if (axes != null && axes.length() > 0) {
                    append("  可变轴：")
                    for (axisIndex in 0 until axes.length()) {
                        val axis = axes.optJSONObject(axisIndex) ?: continue
                        if (axisIndex > 0) append("；")
                        append(axis.optString("tag"))
                            .append(' ')
                            .append(trimNumber(axis.optDouble("min")))
                            .append("–")
                            .append(trimNumber(axis.optDouble("max")))
                            .append("，默认 ")
                            .append(trimNumber(axis.optDouble("default")))
                    }
                    append('\n')
                } else {
                    append("  可变轴：无\n")
                }
                if (index < faces.length() - 1) append('\n')
            }
        }.trimEnd()
        FontDetails(title = title, text = text)
    } catch (error: Throwable) {
        FontDetails(title = font.name, text = error.message ?: "字体详情读取失败")
    }
}

private fun queryDisplayName(context: Context, uri: Uri): String? {
    context.contentResolver.query(
        uri,
        arrayOf(OpenableColumns.DISPLAY_NAME),
        null,
        null,
        null,
    )?.use { cursor ->
        if (cursor.moveToFirst()) {
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0) return cursor.getString(index)?.substringAfterLast('/')
        }
    }
    return uri.lastPathSegment?.substringAfterLast('/')
}

private fun copyUriWithLimit(context: Context, uri: Uri, target: File) {
    context.contentResolver.openInputStream(uri)?.use { input ->
        FileOutputStream(target).use { output ->
            val buffer = ByteArray(128 * 1024)
            var total = 0L
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                total += count
                require(total <= MAX_IMPORT_BYTES) { "文件超过 256 MB 限制" }
                output.write(buffer, 0, count)
            }
            require(total > 0L) { "文件为空" }
            output.fd.sync()
        }
    } ?: error("无法读取所选文件")
}

private fun firstJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("模块没有返回 JSON 数据")
    return JSONObject(line.trim())
}

private fun formatBytes(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "%.1f KB".format(bytes / 1024.0)
    bytes < 1024L * 1024L * 1024L -> "%.1f MB".format(bytes / 1024.0 / 1024.0)
    else -> "%.2f GB".format(bytes / 1024.0 / 1024.0 / 1024.0)
}

private fun trimNumber(value: Double): String {
    val rounded = value.toLong()
    return if (value == rounded.toDouble()) {
        rounded.toString()
    } else {
        "%.2f".format(value).trimEnd('0').trimEnd('.')
    }
}
