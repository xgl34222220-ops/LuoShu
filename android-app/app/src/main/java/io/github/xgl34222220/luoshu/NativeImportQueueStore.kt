package io.github.xgl34222220.luoshu

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.io.StringReader
import java.io.StringWriter
import java.nio.charset.StandardCharsets
import java.util.Base64
import java.util.Properties

internal enum class ImportQueueItemStatus {
    PENDING, RUNNING, IMPORTED, DUPLICATE, FAILED, CANCELLED;

    val terminal: Boolean
        get() = this == IMPORTED || this == DUPLICATE || this == FAILED || this == CANCELLED
}

internal data class ImportQueueItem(
    val uri: String,
    val displayName: String,
    val status: ImportQueueItemStatus = ImportQueueItemStatus.PENDING,
    val error: String = "",
    val persistedPermission: Boolean = false,
)

internal data class ImportQueueTask(
    val taskId: String,
    val phase: NativeImportPhase,
    val createdAt: Long,
    val message: String,
    val recovered: Boolean = false,
    val items: List<ImportQueueItem>,
) {
    val total: Int get() = items.size
    val processed: Int get() = items.count { it.status.terminal }
    val imported: Int get() = items.count { it.status == ImportQueueItemStatus.IMPORTED }
    val duplicates: Int get() = items.count { it.status == ImportQueueItemStatus.DUPLICATE }
    val cancelled: Int get() = items.count { it.status == ImportQueueItemStatus.CANCELLED }
    val failures: List<String> get() = items.filter { it.status == ImportQueueItemStatus.FAILED }.map {
        "${it.displayName}：${it.error.ifBlank { "导入失败" }}"
    }
    val unfinished: Boolean get() = items.any { !it.status.terminal }

    fun forResume(): ImportQueueTask = copy(
        phase = NativeImportPhase.QUEUED,
        message = "检测到未完成导入任务，正在恢复队列",
        recovered = true,
        items = items.map {
            if (it.status == ImportQueueItemStatus.RUNNING) {
                it.copy(status = ImportQueueItemStatus.PENDING, error = "")
            } else {
                it
            }
        },
    )

    fun forManualResume(): ImportQueueTask = copy(
        phase = NativeImportPhase.QUEUED,
        message = "继续导入剩余 ${items.count { !it.status.terminal }} 个文件",
        items = items.map {
            if (it.status == ImportQueueItemStatus.RUNNING) {
                it.copy(status = ImportQueueItemStatus.PENDING, error = "")
            } else {
                it
            }
        },
    )

    fun forRetryFailures(): ImportQueueTask = copy(
        phase = NativeImportPhase.QUEUED,
        message = "准备重试 ${items.count { it.status == ImportQueueItemStatus.FAILED }} 个失败文件",
        recovered = false,
        items = items.map {
            if (it.status == ImportQueueItemStatus.FAILED) {
                it.copy(status = ImportQueueItemStatus.PENDING, error = "")
            } else {
                it
            }
        },
    )

    fun cancelRemaining(): ImportQueueTask = copy(
        phase = NativeImportPhase.CANCELLED,
        message = "字体导入已取消，剩余文件未处理",
        items = items.map {
            if (it.status == ImportQueueItemStatus.PENDING || it.status == ImportQueueItemStatus.RUNNING) {
                it.copy(status = ImportQueueItemStatus.CANCELLED, error = "")
            } else {
                it
            }
        },
    )

    fun toUiState(resultVisible: Boolean = false, refreshToken: Long = 0L): NativeImportState = NativeImportState(
        taskId = taskId,
        phase = phase,
        total = total,
        processed = processed,
        imported = imported,
        duplicates = duplicates,
        cancelled = cancelled,
        failed = failures,
        currentFile = items.firstOrNull { it.status == ImportQueueItemStatus.RUNNING }?.displayName.orEmpty(),
        message = message,
        resultVisible = resultVisible,
        refreshToken = refreshToken,
        recovered = recovered,
    )
}

internal fun encodeImportQueue(task: ImportQueueTask): String {
    val properties = Properties()
    properties.setProperty("schema", "1")
    properties.setProperty("taskId", task.taskId)
    properties.setProperty("phase", task.phase.wireName)
    properties.setProperty("createdAt", task.createdAt.toString())
    properties.setProperty("message", encodeField(task.message))
    properties.setProperty("recovered", task.recovered.toString())
    properties.setProperty("count", task.items.size.toString())
    task.items.forEachIndexed { index, item ->
        properties.setProperty("$index.uri", encodeField(item.uri))
        properties.setProperty("$index.name", encodeField(item.displayName))
        properties.setProperty("$index.status", item.status.name)
        properties.setProperty("$index.error", encodeField(item.error))
        properties.setProperty("$index.persisted", item.persistedPermission.toString())
    }
    return StringWriter().also { properties.store(it, null) }.toString()
}

internal fun decodeImportQueue(raw: String): ImportQueueTask? = runCatching {
    val properties = Properties().apply { load(StringReader(raw)) }
    require(properties.getProperty("schema") == "1")
    val taskId = properties.getProperty("taskId").orEmpty()
    require(taskId.matches(Regex("[A-Za-z0-9._-]{1,96}")))
    val phase = NativeImportPhase.entries.firstOrNull { it.wireName == properties.getProperty("phase") }
        ?: NativeImportPhase.IDLE
    val count = properties.getProperty("count")?.toIntOrNull()?.coerceIn(1, 32) ?: 1
    val items = buildList {
        repeat(count) { index ->
            val uri = decodeField(properties.getProperty("$index.uri").orEmpty())
            val name = decodeField(properties.getProperty("$index.name").orEmpty())
            if (uri.isBlank() || name.isBlank()) return@repeat
            add(
                ImportQueueItem(
                    uri = uri,
                    displayName = name,
                    status = runCatching {
                        ImportQueueItemStatus.valueOf(properties.getProperty("$index.status").orEmpty())
                    }.getOrDefault(ImportQueueItemStatus.PENDING),
                    error = decodeField(properties.getProperty("$index.error").orEmpty()),
                    persistedPermission = properties.getProperty("$index.persisted").toBoolean(),
                ),
            )
        }
    }
    require(items.isNotEmpty())
    ImportQueueTask(
        taskId = taskId,
        phase = phase,
        createdAt = properties.getProperty("createdAt")?.toLongOrNull() ?: 0L,
        message = decodeField(properties.getProperty("message").orEmpty()).ifBlank { "字体导入任务" },
        recovered = properties.getProperty("recovered").toBoolean(),
        items = items,
    )
}.getOrNull()

private fun encodeField(value: String): String = Base64.getUrlEncoder().withoutPadding()
    .encodeToString(value.toByteArray(StandardCharsets.UTF_8))

private fun decodeField(value: String): String = if (value.isBlank()) "" else runCatching {
    String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8)
}.getOrDefault("")

internal class NativeImportQueueStore(context: Context) {
    private val root = File(context.filesDir, "native_import_queue")
    private val stateFile = File(root, "task.properties")

    fun load(): ImportQueueTask? = if (stateFile.isFile) {
        decodeImportQueue(runCatching { stateFile.readText() }.getOrDefault(""))
    } else {
        null
    }

    fun save(task: ImportQueueTask) {
        root.mkdirs()
        val temporary = File(root, "task.properties.tmp")
        FileOutputStream(temporary).use {
            it.write(encodeImportQueue(task).toByteArray(StandardCharsets.UTF_8))
            it.fd.sync()
        }
        if (!temporary.renameTo(stateFile)) {
            FileOutputStream(stateFile).use {
                it.write(temporary.readBytes())
                it.fd.sync()
            }
            temporary.delete()
        }
    }

    fun clear() {
        runCatching { stateFile.delete() }
        runCatching { File(root, "task.properties.tmp").delete() }
    }

    fun stagedFile(taskId: String, index: Int, displayName: String): File {
        val extension = displayName.substringAfterLast('.', "bin").lowercase().take(8)
        val directory = File(root, taskId).apply { mkdirs() }
        return File(directory, "$index.$extension")
    }

    fun partialFile(taskId: String, index: Int, displayName: String): File =
        File(stagedFile(taskId, index, displayName).absolutePath + ".part")
}
