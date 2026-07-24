package io.github.xgl34222220.luoshu.ui.library

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Folder
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.NativeImportViewModel
import io.github.xgl34222220.luoshu.rememberNativeImportViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import java.util.ArrayDeque
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val FONT_WATCH_SCHEMA = 1
private const val FONT_WATCH_MAX_DOCUMENTS = 2_048
private const val FONT_WATCH_MAX_DEPTH = 6
private val FONT_WATCH_EXTENSIONS = setOf("ttf", "otf", "ttc", "zip")

@Immutable
internal data class WatchedFontDocument(
    val key: String,
    val name: String,
    val uri: String,
    val size: Long,
    val modified: Long,
)

@Immutable
internal data class FontDirectoryDiff(
    val added: List<WatchedFontDocument> = emptyList(),
    val changed: List<WatchedFontDocument> = emptyList(),
    val removed: List<WatchedFontDocument> = emptyList(),
) {
    val actionable: List<WatchedFontDocument> get() = added + changed
    val hasChanges: Boolean get() = added.isNotEmpty() || changed.isNotEmpty() || removed.isNotEmpty()
}

@Immutable
internal data class FontDirectoryWatchConfig(
    val treeUri: String = "",
    val label: String = "",
    val snapshot: Map<String, WatchedFontDocument> = emptyMap(),
) {
    val configured: Boolean get() = treeUri.isNotBlank()
}

@Immutable
private data class FontDirectoryScan(
    val documents: List<WatchedFontDocument>,
    val diff: FontDirectoryDiff,
)

internal class FontDirectoryWatchStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "font-directory-watch-v1",
        Context.MODE_PRIVATE,
    )

    fun load(): FontDirectoryWatchConfig = runCatching {
        val root = JSONObject(preferences.getString("config", "{}") ?: "{}")
        if (root.optInt("schema", -1) != FONT_WATCH_SCHEMA) return@runCatching FontDirectoryWatchConfig()
        val snapshotArray = root.optJSONArray("snapshot") ?: JSONArray()
        val snapshot = buildMap {
            for (index in 0 until snapshotArray.length()) {
                val item = snapshotArray.optJSONObject(index) ?: continue
                val document = WatchedFontDocument(
                    key = item.optString("key").trim(),
                    name = item.optString("name").trim(),
                    uri = item.optString("uri").trim(),
                    size = item.optLong("size", -1L),
                    modified = item.optLong("modified", 0L),
                )
                if (document.key.isNotBlank() && document.uri.isNotBlank()) put(document.key, document)
            }
        }
        FontDirectoryWatchConfig(
            treeUri = root.optString("treeUri").trim(),
            label = root.optString("label").trim(),
            snapshot = snapshot,
        )
    }.getOrDefault(FontDirectoryWatchConfig())

    fun save(config: FontDirectoryWatchConfig) {
        val snapshot = JSONArray().apply {
            config.snapshot.values.sortedBy { it.key }.forEach { document ->
                put(
                    JSONObject()
                        .put("key", document.key)
                        .put("name", document.name)
                        .put("uri", document.uri)
                        .put("size", document.size)
                        .put("modified", document.modified),
                )
            }
        }
        val root = JSONObject()
            .put("schema", FONT_WATCH_SCHEMA)
            .put("treeUri", config.treeUri)
            .put("label", config.label)
            .put("snapshot", snapshot)
        preferences.edit().putString("config", root.toString()).apply()
    }

    fun clear() {
        preferences.edit().clear().apply()
    }
}

internal fun diffFontDirectorySnapshots(
    previous: Map<String, WatchedFontDocument>,
    current: List<WatchedFontDocument>,
): FontDirectoryDiff {
    val currentMap = current.associateBy { it.key }
    val added = current.filter { it.key !in previous }
    val changed = current.filter { document ->
        val old = previous[document.key] ?: return@filter false
        old.size != document.size || old.modified != document.modified || old.uri != document.uri
    }
    val removed = previous.values.filter { it.key !in currentMap }
    return FontDirectoryDiff(
        added = added.sortedBy { it.key },
        changed = changed.sortedBy { it.key },
        removed = removed.sortedBy { it.key },
    )
}

internal fun hasPersistedFontDirectoryPermission(context: Context, config: FontDirectoryWatchConfig): Boolean {
    if (!config.configured) return false
    return context.contentResolver.persistedUriPermissions.any { permission ->
        permission.isReadPermission && permission.uri.toString() == config.treeUri
    }
}

@Composable
internal fun FontDirectoryMonitorTool(
    style: UiStyle,
    enabled: Boolean,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val store = remember(context.applicationContext) { FontDirectoryWatchStore(context.applicationContext) }
    val importViewModel = rememberNativeImportViewModel()
    var config by remember { mutableStateOf(store.load()) }
    var scan by remember { mutableStateOf<FontDirectoryScan?>(null) }
    var scanning by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf("") }
    var showDialog by remember { mutableStateOf(false) }

    fun requestScan(target: FontDirectoryWatchConfig = config) {
        if (!target.configured || scanning) return
        scope.launch {
            scanning = true
            errorMessage = ""
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    val documents = scanFontDirectory(context, Uri.parse(target.treeUri))
                    FontDirectoryScan(documents, diffFontDirectorySnapshots(target.snapshot, documents))
                }
            }
            scan = result.getOrNull()
            errorMessage = result.exceptionOrNull()?.message.orEmpty()
            scanning = false
        }
    }

    LaunchedEffect(config.treeUri) {
        if (config.configured) requestScan(config)
    }

    val treeLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val permissionResult = runCatching {
                context.contentResolver.takePersistableUriPermission(
                    uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
            if (permissionResult.isFailure) {
                errorMessage = "无法保留目录读取权限：${permissionResult.exceptionOrNull()?.message.orEmpty()}"
                showDialog = true
                return@launch
            }
            if (config.configured && config.treeUri != uri.toString()) {
                runCatching {
                    context.contentResolver.releasePersistableUriPermission(
                        Uri.parse(config.treeUri),
                        Intent.FLAG_GRANT_READ_URI_PERMISSION,
                    )
                }
            }
            val next = FontDirectoryWatchConfig(
                treeUri = uri.toString(),
                label = withContext(Dispatchers.IO) { queryTreeLabel(context, uri) },
                snapshot = emptyMap(),
            )
            store.save(next)
            config = next
            scan = null
            showDialog = true
        }
    }

    val diff = scan?.diff
    FontDirectoryMonitorButton(
        style = style,
        enabled = enabled,
        configured = config.configured,
        scanning = scanning,
        added = diff?.added?.size ?: 0,
        changed = diff?.changed?.size ?: 0,
        onClick = { showDialog = true },
        modifier = modifier,
    )

    if (showDialog) {
        FontDirectoryMonitorDialog(
            style = style,
            config = config,
            scan = scan,
            scanning = scanning,
            errorMessage = errorMessage,
            importViewModel = importViewModel,
            onChooseDirectory = { treeLauncher.launch(Uri.parse(config.treeUri).takeIf { config.configured }) },
            onScan = { requestScan() },
            onImport = { documents ->
                importViewModel.startImport(documents.take(32).map { Uri.parse(it.uri) })
                val current = scan?.documents.orEmpty().associateBy { it.key }
                val next = config.copy(snapshot = current)
                store.save(next)
                config = next
                scan = scan?.copy(diff = FontDirectoryDiff())
            },
            onUseBaseline = {
                val current = scan?.documents.orEmpty().associateBy { it.key }
                val next = config.copy(snapshot = current)
                store.save(next)
                config = next
                scan = scan?.copy(diff = FontDirectoryDiff())
            },
            onDisconnect = {
                runCatching {
                    context.contentResolver.releasePersistableUriPermission(
                        Uri.parse(config.treeUri),
                        Intent.FLAG_GRANT_READ_URI_PERMISSION,
                    )
                }
                store.clear()
                config = FontDirectoryWatchConfig()
                scan = null
                errorMessage = ""
            },
            onDismiss = { showDialog = false },
        )
    }
}

@Composable
private fun FontDirectoryMonitorButton(
    style: UiStyle,
    enabled: Boolean,
    configured: Boolean,
    scanning: Boolean,
    added: Int,
    changed: Int,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 19.dp),
        color = MaterialTheme.colorScheme.secondaryContainer,
        contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (scanning) {
                CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp)
            } else {
                Icon(Icons.Rounded.Folder, contentDescription = null, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.size(8.dp))
            Column(Modifier.weight(1f)) {
                Text("监视字体目录", fontSize = 11.sp, fontWeight = FontWeight.Black)
                Text(
                    when {
                        !configured -> "选择 SAF 目录"
                        scanning -> "正在扫描目录"
                        added + changed > 0 -> "新增 $added · 变更 $changed"
                        else -> "目录已连接"
                    },
                    fontSize = 9.sp,
                    color = MaterialTheme.colorScheme.onSecondaryContainer.copy(alpha = .72f),
                )
            }
        }
    }
}

@Composable
private fun FontDirectoryMonitorDialog(
    style: UiStyle,
    config: FontDirectoryWatchConfig,
    scan: FontDirectoryScan?,
    scanning: Boolean,
    errorMessage: String,
    importViewModel: NativeImportViewModel,
    onChooseDirectory: () -> Unit,
    onScan: () -> Unit,
    onImport: (List<WatchedFontDocument>) -> Unit,
    onUseBaseline: () -> Unit,
    onDisconnect: () -> Unit,
    onDismiss: () -> Unit,
) {
    val diff = scan?.diff ?: FontDirectoryDiff()
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
            shadowElevation = 14.dp,
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(46.dp),
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.secondaryContainer,
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
                            Icon(Icons.Rounded.Folder, contentDescription = null)
                        }
                    }
                    Spacer(Modifier.size(11.dp))
                    Column(Modifier.weight(1f)) {
                        Text("SAF 字体目录监视", fontSize = 19.sp, fontWeight = FontWeight.Black)
                        Text(
                            "进入字体库时扫描，不在后台常驻",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                        )
                    }
                    IconButton(onClick = onDismiss) { Icon(Icons.Rounded.Close, contentDescription = "关闭") }
                }

                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(20.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerLow,
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Text(
                            if (config.configured) config.label.ifBlank { "已选择目录" } else "尚未选择目录",
                            fontWeight = FontWeight.Black,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            when {
                                scanning -> "正在读取受支持的 TTF、OTF、TTC 与 ZIP 文件"
                                scan != null -> "发现 ${scan.documents.size} 个文件 · 新增 ${diff.added.size} · 变更 ${diff.changed.size} · 移除 ${diff.removed.size}"
                                else -> "选择目录后会建立安全扫描基线"
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                        )
                    }
                }

                if (errorMessage.isNotBlank()) {
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(18.dp),
                        color = MaterialTheme.colorScheme.errorContainer,
                    ) {
                        Row(Modifier.padding(11.dp), verticalAlignment = Alignment.Top) {
                            Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.size(7.dp))
                            Text(errorMessage, modifier = Modifier.weight(1f), fontSize = 10.sp)
                        }
                    }
                }

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onChooseDirectory, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Rounded.Folder, contentDescription = null, modifier = Modifier.size(17.dp))
                        Spacer(Modifier.size(5.dp))
                        Text(if (config.configured) "更换目录" else "选择目录")
                    }
                    OutlinedButton(
                        onClick = onScan,
                        enabled = config.configured && !scanning,
                        modifier = Modifier.weight(1f),
                    ) {
                        if (scanning) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                        else Icon(Icons.Rounded.Refresh, contentDescription = null, modifier = Modifier.size(17.dp))
                        Spacer(Modifier.size(5.dp))
                        Text("重新扫描")
                    }
                }

                if (diff.hasChanges) {
                    Text(
                        "新增与变更会进入现有安全导入队列；目录删除只作提示，洛书不会自动删除字体库文件。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        lineHeight = 14.sp,
                    )
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = onUseBaseline, modifier = Modifier.weight(1f)) {
                            Text("仅记录基线")
                        }
                        OutlinedButton(
                            onClick = { onImport(diff.actionable) },
                            enabled = diff.actionable.isNotEmpty() && !importViewModel.state.busy && !importViewModel.state.paused,
                            modifier = Modifier.weight(1f),
                        ) {
                            Text(if (diff.actionable.size > 32) "导入前 32 项" else "导入 ${diff.actionable.size} 项")
                        }
                    }
                }

                if (config.configured) {
                    TextButton(onClick = onDisconnect, modifier = Modifier.align(Alignment.Start)) {
                        Text("断开目录监视", color = MaterialTheme.colorScheme.error)
                    }
                }
                TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) {
                    Text("完成", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

private fun scanFontDirectory(context: Context, treeUri: Uri): List<WatchedFontDocument> {
    require(hasPersistedFontDirectoryPermission(context, FontDirectoryWatchConfig(treeUri = treeUri.toString()))) {
        "目录读取权限已失效，请重新选择目录"
    }
    val resolver = context.contentResolver
    val rootId = DocumentsContract.getTreeDocumentId(treeUri)
    val queue = ArrayDeque<Triple<String, String, Int>>()
    queue.add(Triple(rootId, "", 0))
    val documents = mutableListOf<WatchedFontDocument>()
    val projection = arrayOf(
        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
        DocumentsContract.Document.COLUMN_MIME_TYPE,
        DocumentsContract.Document.COLUMN_SIZE,
        DocumentsContract.Document.COLUMN_LAST_MODIFIED,
    )

    while (queue.isNotEmpty() && documents.size < FONT_WATCH_MAX_DOCUMENTS) {
        val (parentId, prefix, depth) = queue.removeFirst()
        val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentId)
        resolver.query(childrenUri, projection, null, null, null)?.use { cursor ->
            val idIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
            val nameIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DISPLAY_NAME)
            val mimeIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE)
            val sizeIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_SIZE)
            val modifiedIndex = cursor.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
            while (cursor.moveToNext() && documents.size < FONT_WATCH_MAX_DOCUMENTS) {
                val documentId = cursor.getString(idIndex)
                val name = cursor.getString(nameIndex).orEmpty().substringAfterLast('/')
                val mime = cursor.getString(mimeIndex).orEmpty()
                val relativePath = if (prefix.isBlank()) name else "$prefix/$name"
                if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                    if (depth < FONT_WATCH_MAX_DEPTH) queue.add(Triple(documentId, relativePath, depth + 1))
                    continue
                }
                val extension = name.substringAfterLast('.', "").lowercase()
                if (extension !in FONT_WATCH_EXTENSIONS) continue
                val documentUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, documentId)
                documents += WatchedFontDocument(
                    key = relativePath.lowercase(),
                    name = name,
                    uri = documentUri.toString(),
                    size = if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) cursor.getLong(sizeIndex) else -1L,
                    modified = if (modifiedIndex >= 0 && !cursor.isNull(modifiedIndex)) cursor.getLong(modifiedIndex) else 0L,
                )
            }
        }
    }
    return documents.sortedBy { it.key }
}

private fun queryTreeLabel(context: Context, treeUri: Uri): String {
    return runCatching {
        val rootId = DocumentsContract.getTreeDocumentId(treeUri)
        val rootUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, rootId)
        context.contentResolver.query(
            rootUri,
            arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0).orEmpty() else ""
        }.orEmpty()
    }.getOrDefault("").ifBlank { "字体监视目录" }
}
