package io.github.xgl34222220.luoshu

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.SystemClock
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val IMPORT_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"
private const val MAX_IMPORT_BYTES = 268_435_456L
private const val IMPORT_CHECKPOINT_ITEMS = 5
private const val IMPORT_CHECKPOINT_INTERVAL_MS = 1_500L
private const val IMPORT_CACHE_MAX_AGE_MS = 3_600_000L
private val ALLOWED_IMPORT_EXTENSIONS = setOf("ttf", "otf", "ttc", "zip")

internal enum class NativeImportPhase(val wireName: String) {
    IDLE("idle"),
    QUEUED("queued"),
    RUNNING("running"),
    PAUSED("paused"),
    SUCCESS("success"),
    FAILED("failed"),
    CANCELLED("cancelled"),
}

@Immutable
internal data class NativeImportState(
    val taskId: String = "",
    val phase: NativeImportPhase = NativeImportPhase.IDLE,
    val total: Int = 0,
    val processed: Int = 0,
    val imported: Int = 0,
    val duplicates: Int = 0,
    val cancelled: Int = 0,
    val failed: List<String> = emptyList(),
    val currentFile: String = "",
    val message: String = "尚未开始导入",
    val resultVisible: Boolean = false,
    val refreshToken: Long = 0L,
    val recovered: Boolean = false,
) {
    val busy: Boolean
        get() = phase == NativeImportPhase.QUEUED || phase == NativeImportPhase.RUNNING

    val paused: Boolean
        get() = phase == NativeImportPhase.PAUSED

    val terminal: Boolean
        get() = phase == NativeImportPhase.SUCCESS ||
            phase == NativeImportPhase.FAILED ||
            phase == NativeImportPhase.CANCELLED

    val canPause: Boolean get() = busy
    val canResume: Boolean get() = paused
    val canCancel: Boolean get() = busy || paused
    val canRetryFailed: Boolean get() = terminal && failed.isNotEmpty()
    val canClear: Boolean get() = !busy && phase != NativeImportPhase.IDLE

    val progress: Int
        get() = when {
            total <= 0 -> 0
            processed >= total -> 100
            else -> ((processed * 100) / total).coerceIn(0, 99)
        }

    val title: String
        get() = when {
            paused -> "字体导入已暂停"
            phase == NativeImportPhase.CANCELLED -> "字体导入已取消"
            busy && recovered -> "正在恢复字体导入"
            busy -> "正在导入字体"
            failed.isEmpty() -> "导入完成"
            imported > 0 || duplicates > 0 -> "导入部分完成"
            else -> "导入失败"
        }

    val summary: String
        get() = buildString {
            if (phase == NativeImportPhase.CANCELLED) {
                append("已处理 ").append(processed - cancelled).append('/').append(total).append(" 个文件")
            } else {
                append("成功导入 ").append(imported).append(" 个文件")
            }
            if (duplicates > 0) append("，跳过 ").append(duplicates).append(" 个重复字体")
            if (cancelled > 0) append("，取消 ").append(cancelled).append(" 个待处理文件")
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
    private var lastCheckpointProcessed = -1
    private var lastCheckpointAt = 0L

    @Volatile
    private var pauseRequested = false

    @Volatile
    private var cancelRequested = false

    init {
        restoreSavedTask()
    }

    fun startImport(uris: List<Uri>) {
        if (state.busy || state.paused || importJob?.isActive == true) return
        val unique = uris.distinctBy(Uri::toString)
        val selected = unique.take(MAX_IMPORT_QUEUE_ITEMS)
        if (selected.isEmpty()) return
        val truncated = unique.size - selected.size
        state = NativeImportState(
            phase = NativeImportPhase.QUEUED,
            total = selected.size,
            message = if (truncated > 0) {
                "正在准备 ${selected.size} 个文件；已忽略超出上限的 $truncated 个文件"
            } else {
                "正在准备 ${selected.size} 个文件的导入队列"
            },
        )

        importJob = viewModelScope.launch {
            val context = getApplication<Application>().applicationContext
            var preparedItems: List<ImportQueueItem> = emptyList()
            try {
                withContext(Dispatchers.IO) {
                    discardPreviousRecord(context)
                    cleanupImportCache(context, includeRecent = false)
                }
                preparedItems = withContext(Dispatchers.IO) {
                    selected.mapIndexed { index, uri ->
                        currentCoroutineContext().ensureActive()
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
                pauseRequested = false
                cancelRequested = false
                val task = ImportQueueTask(
                    taskId = "import-${System.currentTimeMillis()}",
                    phase = NativeImportPhase.QUEUED,
                    createdAt = System.currentTimeMillis(),
                    message = if (truncated > 0) {
                        "已保存 ${preparedItems.size} 个文件；超出上限的 $truncated 个文件未加入"
                    } else {
                        "已保存 ${preparedItems.size} 个文件的导入队列"
                    },
                    items = preparedItems,
                )
                runQueue(task)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                if (preparedItems.isNotEmpty()) {
                    withContext(Dispatchers.IO) {
                        releasePermissions(
                            context,
                            ImportQueueTask(
                                taskId = "prepare-failed",
                                phase = NativeImportPhase.FAILED,
                                createdAt = System.currentTimeMillis(),
                                message = "准备导入失败",
                                items = preparedItems,
                            ),
                            includeFailures = true,
                        )
                    }
                }
                state = NativeImportState(
                    phase = NativeImportPhase.FAILED,
                    total = selected.size,
                    failed = listOf(error.message ?: "准备导入队列失败"),
                    message = error.message ?: "准备导入队列失败",
                    resultVisible = true,
                )
            } finally {
                importJob = null
            }
        }
    }

    fun pauseImport() {
        if (!state.canPause) return
        pauseRequested = true
        state = state.copy(
            message = if (state.phase == NativeImportPhase.RUNNING) {
                "当前文件完成后暂停导入队列"
            } else {
                "正在暂停导入队列"
            },
        )
    }

    fun resumeImport() {
        if (!state.canResume || importJob?.isActive == true) return
        importJob = viewModelScope.launch {
            try {
                val saved = withContext(Dispatchers.IO) { queueStore.load() } ?: return@launch
                pauseRequested = false
                cancelRequested = false
                runQueue(saved.forManualResume())
            } finally {
                importJob = null
            }
        }
    }

    fun cancelImport() {
        if (!state.canCancel) return
        if (state.paused && importJob?.isActive != true) {
            importJob = viewModelScope.launch {
                try {
                    val saved = withContext(Dispatchers.IO) { queueStore.load() } ?: return@launch
                    finishCancelled(saved)
                } finally {
                    importJob = null
                }
            }
            return
        }
        cancelRequested = true
        pauseRequested = false
        state = state.copy(message = "当前文件完成后取消剩余导入")
    }

    fun retryFailed() {
        if (!state.canRetryFailed || importJob?.isActive == true) return
        importJob = viewModelScope.launch {
            try {
                val saved = withContext(Dispatchers.IO) { queueStore.load() } ?: return@launch
                if (saved.failures.isEmpty()) return@launch
                pauseRequested = false
                cancelRequested = false
                runQueue(saved.forRetryFailures())
            } finally {
                importJob = null
            }
        }
    }

    fun clearRecord() {
        if (!state.canClear || importJob?.isActive == true) return
        importJob = viewModelScope.launch {
            try {
                val context = getApplication<Application>().applicationContext
                val saved = withContext(Dispatchers.IO) { queueStore.load() }
                withContext(Dispatchers.IO) {
                    if (saved != null) releasePermissions(context, saved, includeFailures = true)
                    queueStore.clear()
                    cleanupImportCache(context, includeRecent = true)
                }
                pauseRequested = false
                cancelRequested = false
                state = NativeImportState()
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
                when {
                    saved.phase == NativeImportPhase.PAUSED -> state = saved.toUiState(resultVisible = false)
                    saved.phase == NativeImportPhase.SUCCESS ||
                        saved.phase == NativeImportPhase.FAILED ||
                        saved.phase == NativeImportPhase.CANCELLED -> state = saved.toUiState(resultVisible = false)
                    saved.unfinished -> runQueue(saved.forResume())
                    else -> state = saved.toUiState(resultVisible = false)
                }
            } finally {
                importJob = null
            }
        }
    }

    private suspend fun runQueue(initial: ImportQueueTask) {
        var task = initial
        lastCheckpointProcessed = -1
        lastCheckpointAt = 0L
        persistAndPublish(task, forceCheckpoint = true)

        task.items.indices.forEach { index ->
            currentCoroutineContext().ensureActive()
            if (cancelRequested) {
                if (task.unfinished) finishCancelled(task) else finishCompleted(task)
                return
            }
            if (pauseRequested) {
                if (task.unfinished) finishPaused(task) else finishCompleted(task)
                return
            }

            val item = task.items[index]
            if (item.status.terminal) return@forEach

            task = task.replaceItem(
                index,
                item.copy(status = ImportQueueItemStatus.RUNNING, error = ""),
            ).copy(
                phase = NativeImportPhase.RUNNING,
                message = "正在导入 ${task.processed + 1}/${task.total}：${item.displayName}",
            )
            publishOnly(task)

            val context = getApplication<Application>().applicationContext
            val resultItem = try {
                when (withContext(Dispatchers.IO) { importOne(context, Uri.parse(item.uri), item.displayName) }) {
                    ImportOutcome.IMPORTED -> item.copy(status = ImportQueueItemStatus.IMPORTED, error = "")
                    ImportOutcome.DUPLICATE -> item.copy(status = ImportQueueItemStatus.DUPLICATE, error = "")
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                item.copy(
                    status = ImportQueueItemStatus.FAILED,
                    error = error.message ?: "导入失败",
                )
            }
            task = task.replaceItem(index, resultItem).copy(
                message = "已处理 ${task.processed + 1}/${task.total}：${item.displayName}",
            )
            persistAndPublish(task)

            if (cancelRequested) {
                if (task.unfinished) finishCancelled(task) else finishCompleted(task)
                return
            }
            if (pauseRequested) {
                if (task.unfinished) finishPaused(task) else finishCompleted(task)
                return
            }
        }

        finishCompleted(task)
    }

    private suspend fun finishPaused(task: ImportQueueTask) {
        pauseRequested = false
        val paused = task.copy(
            phase = NativeImportPhase.PAUSED,
            message = "导入已暂停，已处理 ${task.processed}/${task.total} 个文件",
        )
        persistAndPublish(paused, forceCheckpoint = true)
    }

    private suspend fun finishCancelled(task: ImportQueueTask) {
        cancelRequested = false
        pauseRequested = false
        val cancelled = task.cancelRemaining()
        persistAndPublish(
            cancelled,
            resultVisible = true,
            refreshToken = if (cancelled.imported > 0) System.currentTimeMillis() else 0L,
            forceCheckpoint = true,
        )
        val context = getApplication<Application>().applicationContext
        withContext(Dispatchers.IO) {
            releasePermissions(context, cancelled, includeFailures = false)
            cleanupImportCache(context, includeRecent = true)
        }
    }

    private suspend fun finishCompleted(task: ImportQueueTask) {
        pauseRequested = false
        cancelRequested = false
        val phase = if (task.failures.isEmpty()) NativeImportPhase.SUCCESS else NativeImportPhase.FAILED
        val message = when {
            task.failures.isEmpty() -> "字体导入完成，共处理 ${task.total} 个文件"
            task.imported > 0 || task.duplicates > 0 -> "字体导入部分完成，${task.failures.size} 个文件失败"
            else -> "字体导入失败，未成功处理任何文件"
        }
        val completed = task.copy(phase = phase, message = message)
        persistAndPublish(
            completed,
            resultVisible = true,
            refreshToken = System.currentTimeMillis(),
            forceCheckpoint = true,
        )
        val context = getApplication<Application>().applicationContext
        withContext(Dispatchers.IO) {
            releasePermissions(context, completed, includeFailures = false)
            cleanupImportCache(context, includeRecent = true)
        }
    }

    private suspend fun persistAndPublish(
        task: ImportQueueTask,
        resultVisible: Boolean = false,
        refreshToken: Long = 0L,
        forceCheckpoint: Boolean = false,
    ) {
        state = task.toUiState(resultVisible = resultVisible, refreshToken = refreshToken)
        val now = SystemClock.elapsedRealtime()
        val shouldCheckpoint = forceCheckpoint ||
            task.phase != NativeImportPhase.RUNNING ||
            task.processed - lastCheckpointProcessed >= IMPORT_CHECKPOINT_ITEMS ||
            now - lastCheckpointAt >= IMPORT_CHECKPOINT_INTERVAL_MS
        if (!shouldCheckpoint) return
        withContext(Dispatchers.IO) { queueStore.save(task) }
        lastCheckpointProcessed = task.processed
        lastCheckpointAt = now
    }

    private fun publishOnly(task: ImportQueueTask) {
        state = task.toUiState()
    }

    private fun ImportQueueTask.replaceItem(index: Int, replacement: ImportQueueItem): ImportQueueTask {
        val updated = items.toMutableList()
        updated[index] = replacement
        return copy(items = updated)
    }

    private fun discardPreviousRecord(context: android.content.Context) {
        queueStore.load()?.let { releasePermissions(context, it, includeFailures = true) }
        queueStore.clear()
    }

    private fun releasePermissions(
        context: android.content.Context,
        task: ImportQueueTask,
        includeFailures: Boolean,
    ) {
        task.items.filter { item ->
            item.persistedPermission && when (item.status) {
                ImportQueueItemStatus.IMPORTED,
                ImportQueueItemStatus.DUPLICATE,
                ImportQueueItemStatus.CANCELLED -> true
                ImportQueueItemStatus.FAILED -> includeFailures
                ImportQueueItemStatus.PENDING,
                ImportQueueItemStatus.RUNNING -> false
            }
        }.forEach { item ->
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
            val buffer = ByteArray(256 * 1024)
            var total = 0L
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                total += count
                require(total <= MAX_IMPORT_BYTES) { "文件超过 256 MB 限制" }
                output.write(buffer, 0, count)
            }
            require(total > 0L) { "文件为空" }
            output.flush()
        }
    } ?: error("无法读取所选文件")
}

private fun cleanupImportCache(context: android.content.Context, includeRecent: Boolean) {
    val cacheDir = File(context.cacheDir, "native_import")
    val now = System.currentTimeMillis()
    cacheDir.listFiles()?.forEach { file ->
        if (file.isFile && (includeRecent || now - file.lastModified() > IMPORT_CACHE_MAX_AGE_MS)) {
            runCatching { file.delete() }
        }
    }
}

private fun firstImportJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("未收到导入结果")
    return JSONObject(line.trim())
}
