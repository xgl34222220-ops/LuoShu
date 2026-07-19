package io.github.xgl34222220.luoshu

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import java.io.File
import java.io.FileOutputStream
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val IMPORT_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"
private const val MAX_IMPORT_BYTES = 268_435_456L
private val ALLOWED_IMPORT_EXTENSIONS = setOf("ttf", "otf", "ttc", "zip")

internal enum class NativeImportPhase(val wireName: String) {
    IDLE("idle"),
    QUEUED("queued"),
    RUNNING("running"),
    SUCCESS("success"),
    FAILED("failed"),
}

@Immutable
internal data class NativeImportState(
    val taskId: String = "",
    val phase: NativeImportPhase = NativeImportPhase.IDLE,
    val total: Int = 0,
    val processed: Int = 0,
    val imported: Int = 0,
    val duplicates: Int = 0,
    val failed: List<String> = emptyList(),
    val currentFile: String = "",
    val message: String = "尚未开始导入",
    val resultVisible: Boolean = false,
    val refreshToken: Long = 0L,
    val recovered: Boolean = false,
) {
    val busy: Boolean
        get() = phase == NativeImportPhase.QUEUED || phase == NativeImportPhase.RUNNING

    val progress: Int
        get() = when {
            total <= 0 -> 0
            processed >= total -> 100
            else -> ((processed * 100) / total).coerceIn(0, 99)
        }

    val title: String
        get() = when {
            busy && recovered -> "正在恢复字体导入"
            busy -> "正在导入字体"
            failed.isEmpty() -> "导入完成"
            imported > 0 || duplicates > 0 -> "导入部分完成"
            else -> "导入失败"
        }

    val summary: String
        get() = buildString {
            append("成功导入 ").append(imported).append(" 个文件")
            if (duplicates > 0) append("，跳过 ").append(duplicates).append(" 个重复字体")
            if (failed.isNotEmpty()) {
                append("\n\n失败：\n")
                failed.take(6).forEach { append("• ").append(it).append('\n') }
                if (failed.size > 6) append("其余 ").append(failed.size - 6).append(" 项请查看任务中心")
            }
        }.trimEnd()
}

private enum class ImportOutcome { IMPORTED, DUPLICATE }

internal class NativeImportViewModel(application: Application) : AndroidViewModel(application) {
    private val queueStore = NativeImportQueueStore(application.applicationContext)

    var state by mutableStateOf(NativeImportState())
        private set

    private var importJob: Job? = null

    init {
        restoreSavedTask()
    }

    fun startImport(uris: List<Uri>) {
        if (state.busy || importJob?.isActive == true) return
        val selected = uris.take(32)
        if (selected.isEmpty()) return

        importJob = viewModelScope.launch {
            try {
                val context = getApplication<Application>().applicationContext
                val items = withContext(Dispatchers.IO) {
                    selected.mapIndexed { index, uri ->
                        val name = queryDisplayName(context, uri) ?: "font-${index + 1}"
                        val persisted = runCatching {
                            context.contentResolver.takePersistableUriPermission(
                                uri,
                                Intent.FLAG_GRANT_READ_URI_PERMISSION,
                            )
                            true
                        }.getOrDefault(false)
                        ImportQueueItem(
                            uri = uri.toString(),
                            displayName = name,
                            persistedPermission = persisted,
                        )
                    }
                }
                val task = ImportQueueTask(
                    taskId = "import-${System.currentTimeMillis()}",
                    phase = NativeImportPhase.QUEUED,
                    createdAt = System.currentTimeMillis(),
                    message = "已保存 ${items.size} 个文件的导入队列",
                    items = items,
                )
                runQueue(task)
            } finally {
                importJob = null
            }
        }
    }

    fun dismissResult() {
        state = state.copy(resultVisible = false)
    }

    private fun restoreSavedTask() {
        importJob = viewModelScope.launch {
            try {
                val saved = withContext(Dispatchers.IO) { queueStore.load() } ?: return@launch
                val active = saved.phase == NativeImportPhase.QUEUED || saved.phase == NativeImportPhase.RUNNING
                if (active || saved.unfinished) {
                    runQueue(saved.forResume())
                } else {
                    state = saved.toUiState(resultVisible = false)
                }
            } finally {
                importJob = null
            }
        }
    }

    private suspend fun runQueue(initial: ImportQueueTask) {
        val context = getApplication<Application>().applicationContext
        var task = initial
        persistAndPublish(task)

        task.items.indices.forEach { index ->
            val item = task.items[index]
            if (item.status.terminal) return@forEach

            task = task.replaceItem(
                index,
                item.copy(status = ImportQueueItemStatus.RUNNING, error = ""),
            ).copy(
                phase = NativeImportPhase.RUNNING,
                message = "正在导入 ${task.processed + 1}/${task.total}：${item.displayName}",
            )
            persistAndPublish(task)

            val resultItem = try {
                when (withContext(Dispatchers.IO) { importOne(context, Uri.parse(item.uri), item.displayName) }) {
                    ImportOutcome.IMPORTED -> item.copy(status = ImportQueueItemStatus.IMPORTED, error = "")
                    ImportOutcome.DUPLICATE -> item.copy(status = ImportQueueItemStatus.DUPLICATE, error = "")
                }
            } catch (error: Throwable) {
                item.copy(
                    status = ImportQueueItemStatus.FAILED,
                    error = error.message ?: "导入失败",
                )
            }
            task = task.replaceItem(index, resultItem)
            persistAndPublish(task)
        }

        val phase = if (task.failures.isEmpty()) NativeImportPhase.SUCCESS else NativeImportPhase.FAILED
        val message = when {
            task.failures.isEmpty() -> "字体导入完成，共处理 ${task.total} 个文件"
            task.imported > 0 || task.duplicates > 0 -> "字体导入部分完成，${task.failures.size} 个文件失败"
            else -> "字体导入失败，未成功处理任何文件"
        }
        task = task.copy(phase = phase, message = message)
        persistAndPublish(task, resultVisible = true, refreshToken = System.currentTimeMillis())
        withContext(Dispatchers.IO) { releasePermissions(context, task) }
    }

    private suspend fun persistAndPublish(
        task: ImportQueueTask,
        resultVisible: Boolean = false,
        refreshToken: Long = 0L,
    ) {
        withContext(Dispatchers.IO) { queueStore.save(task) }
        state = task.toUiState(resultVisible = resultVisible, refreshToken = refreshToken)
    }

    private fun ImportQueueTask.replaceItem(index: Int, replacement: ImportQueueItem): ImportQueueTask =
        copy(items = items.mapIndexed { itemIndex, item -> if (itemIndex == index) replacement else item })

    private fun releasePermissions(context: android.content.Context, task: ImportQueueTask) {
        task.items.filter { it.persistedPermission }.forEach { item ->
            runCatching {
                context.contentResolver.releasePersistableUriPermission(
                    Uri.parse(item.uri),
                    Intent.FLAG_GRANT_READ_URI_PERMISSION,
                )
            }
        }
    }
}

private suspend fun importOne(context: android.content.Context, uri: Uri, displayName: String): ImportOutcome {
    val extension = displayName.substringAfterLast('.', "").lowercase()
    require(extension in ALLOWED_IMPORT_EXTENSIONS) { "仅支持 TTF、OTF、TTC 和 ZIP" }

    val cacheDir = File(context.cacheDir, "native_import")
    cacheDir.mkdirs()
    val temp = File(cacheDir, "${System.currentTimeMillis()}-${UUID.randomUUID()}.$extension")
    try {
        copyUriWithLimit(context, uri, temp)
        val result = RootShell.exec(
            "sh ${RootShell.quote(IMPORT_BRIDGE)} import_file " +
                "${RootShell.quote(temp.absolutePath)} ${RootShell.quote(displayName)}",
            timeoutMs = if (extension == "zip") 180_000L else 60_000L,
        )
        if (result.code != 0) error(result.stderr.ifBlank { "Root 导入失败" })
        val root = firstImportJson(result.stdout)
        if (root.optString("status") != "ok") error(root.optString("message", "导入失败"))
        return if (root.optJSONObject("data")?.optBoolean("duplicate", false) == true) {
            ImportOutcome.DUPLICATE
        } else {
            ImportOutcome.IMPORTED
        }
    } finally {
        temp.delete()
        cacheDir.listFiles()?.filter { it.isFile }?.forEach { file ->
            if (System.currentTimeMillis() - file.lastModified() > 3_600_000L) file.delete()
        }
    }
}

private fun queryDisplayName(context: android.content.Context, uri: Uri): String? {
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

private fun copyUriWithLimit(context: android.content.Context, uri: Uri, target: File) {
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

private fun firstImportJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("未收到导入结果")
    return JSONObject(line.trim())
}
