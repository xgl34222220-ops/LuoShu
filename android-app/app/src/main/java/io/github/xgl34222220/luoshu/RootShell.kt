package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.util.UUID
import org.json.JSONObject

internal data class ShellResult(
    val code: Int,
    val stdout: String,
    val stderr: String,
    val cleanupVerified: Boolean = true,
)

internal object RootShell {
    suspend fun exec(command: String, timeoutMs: Long = 600_000L): ShellResult = withContext(Dispatchers.IO) {
        try {
            executeScopedRequest(command, timeoutMs)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (interrupted: InterruptedException) {
            throw CancellationException("Command cancelled").also { it.initCause(interrupted) }
        } catch (error: Throwable) {
            val raw = error.message.orEmpty()
            if (
                error is IOException &&
                raw.contains("interrupted by close", ignoreCase = true)
            ) {
                return@withContext ShellResult(75, "", "Root 输出暂时中断，请重试", cleanupVerified = !error.cleanupUnconfirmed())
            }
            val message = if (
                error is IOException &&
                (raw.contains("Cannot run program \"su\"") || raw.contains("No such file or directory"))
            ) {
                "未找到 Root 命令 su。请先在 Root 管理器中完成待生效变更并完整重启，然后为洛书授予 Root 权限。"
            } else {
                raw.ifBlank { error.javaClass.simpleName }
            }
            ShellResult(127, "", message, cleanupVerified = !error.cleanupUnconfirmed())
        }
    }

    fun quote(value: String): String = "'" + value.replace("'", "'\\''") + "'"
}

private const val TASK_SCOPE = "/data/adb/modules/LuoShu/common/task_scope.sh"
private const val REQUEST_CLEANUP_TIMEOUT_MS = 20_000L

/** The backend owns descendants by token; the App only owns its local su request. */
internal suspend fun executeScopedRequest(
    command: String,
    timeoutMs: Long,
    token: String = "app-${UUID.randomUUID()}",
    scopePath: String = TASK_SCOPE,
    executor: suspend (List<String>, Long) -> ShellResult = ::executeProcess,
): ShellResult {
    require(timeoutMs > 0L) { "Request timeout must be positive" }
    require(token.length <= 160 && token !in setOf(".", "..") && token.matches(Regex("[A-Za-z0-9._-]+"))) { "Invalid request token" }
    val timeoutSeconds = ((timeoutMs - 1L) / 1_000L + 1L).coerceAtLeast(1L)
    val request = "if [ -f ${RootShell.quote(scopePath)} ]; then " +
        "sh ${RootShell.quote(scopePath)} request-run ${RootShell.quote(token)} $timeoutSeconds -- " +
        "sh -c ${RootShell.quote(command)}; else " +
        "printf '%s\\n' '洛书任务清理组件不可用，请先安装匹配模块' >&2; exit 127; fi"
    try {
        val result = executor(listOf("su", "-c", request), timeoutMs)
        // 125 is the supervisor's fail-closed result when cleanup left descendants.
        if (result.code != 124 && result.code != 125) return result
        val cleanup = cleanupScopedRequest(scopePath, token, executor)
        return if (cleanupConfirmed(cleanup, "token", token)) result else result.copy(
            stderr = "${result.stderr}\n任务清理尚未确认：${cleanup.stderr.ifBlank { "请查看任务日志" }}".trim(),
            cleanupVerified = false,
        )
    } catch (cancelled: CancellationException) {
        val cleanup = cleanupScopedRequest(scopePath, token, executor)
        if (!cleanupConfirmed(cleanup, "token", token)) {
            cancelled.addSuppressed(OwnedTaskCleanupFailure("任务清理尚未确认：${cleanup.stderr.ifBlank { "请查看任务日志" }}"))
        }
        throw cancelled
    } catch (error: Exception) {
        // Pipe/read failures may happen after the command has already spawned children.
        val cleanup = cleanupScopedRequest(scopePath, token, executor)
        if (!cleanupConfirmed(cleanup, "token", token)) {
            error.addSuppressed(OwnedTaskCleanupFailure("任务清理尚未确认：${cleanup.stderr.ifBlank { "请查看任务日志" }}"))
        }
        throw error
    }
}

private suspend fun cleanupScopedRequest(
    scopePath: String,
    token: String,
    executor: suspend (List<String>, Long) -> ShellResult,
): ShellResult = withContext(NonCancellable) {
    // A fresh request survives cancellation of the original coroutine and su process.
    // It can only cancel the verified token; no process-name or App-wide kill is used.
    val cleanup = "sh ${RootShell.quote(scopePath)} request-cancel ${RootShell.quote(token)}"
    try {
        executor(listOf("su", "-c", cleanup), REQUEST_CLEANUP_TIMEOUT_MS)
    } catch (error: Exception) {
        ShellResult(125, "", error.message ?: "任务清理失败")
    }
}

internal fun cleanupConfirmed(result: ShellResult, identityKey: String, identity: String): Boolean {
    if (result.code != 0 || identity.isBlank()) return false
    return runCatching {
        val line = result.stdout.lineSequence().first { it.trimStart().startsWith("{") }
        val root = JSONObject(line)
        val data = root.optJSONObject("data") ?: return@runCatching false
        root.optString("status") == "ok" && data.optBoolean("cleaned", false) &&
            data.optString(identityKey) == identity
    }.getOrDefault(false)
}

internal class OwnedTaskCleanupFailure(message: String) : IOException(message)

internal fun Throwable.cleanupUnconfirmed(): Boolean =
    this is OwnedTaskCleanupFailure || suppressed.any { it is OwnedTaskCleanupFailure }

internal fun ShellResult.requireCleaned() {
    if (!cleanupVerified) throw OwnedTaskCleanupFailure(stderr.ifBlank { "任务清理尚未确认" })
}

/** Stop a known module worker before a failed/cancelled observer releases its busy state. */
internal suspend fun <T> awaitOwnedFontTask(
    taskId: String,
    cancelCommand: String,
    onCleanup: (Boolean, String) -> Unit,
    executor: suspend (String, Long) -> ShellResult = { command, timeout -> RootShell.exec(command, timeout) },
    block: suspend () -> T,
): T {
    require(taskId.isNotBlank()) { "Missing owned font task" }
    try {
        return block()
    } catch (failure: Throwable) {
        val cleaned = withContext(NonCancellable) {
            val cleanup = try {
                executor(cancelCommand, REQUEST_CLEANUP_TIMEOUT_MS)
            } catch (error: Exception) {
                ShellResult(125, "", error.message ?: "字体任务清理失败")
            }
            cleanupConfirmed(cleanup, "task", taskId).also { verified ->
                // Publish while this context still survives the caller's cancellation.
                onCleanup(verified, cleanup.stderr.ifBlank { cleanup.stdout })
            }
        }
        if (!cleaned) failure.addSuppressed(OwnedTaskCleanupFailure("字体任务清理尚未确认"))
        throw failure
    }
}

/** Low-level request IO. Descendant ownership belongs to executeScopedRequest's backend. */
internal suspend fun executeProcess(command: List<String>, timeoutMs: Long): ShellResult =
    withContext(Dispatchers.IO) {
        currentCoroutineContext().ensureActive()
        val process = ProcessBuilder(command).redirectErrorStream(false).start()
        val stdout = ByteArrayOutputStream()
        val stderr = ByteArrayOutputStream()
        val buffer = ByteArray(8_192)
        val startedAt = System.nanoTime()
        try {
            // No command accepts interactive input. Closing stdin also lets commands waiting
            // for EOF finish normally. Never wait for pipe EOF: descendants may inherit it.
            process.outputStream.close()
            while (true) {
                currentCoroutineContext().ensureActive()
                val outputBytes = drainAvailable(process.inputStream, stdout, buffer) +
                    drainAvailable(process.errorStream, stderr, buffer)
                if (!process.isAlive) {
                    // Drain the final bytes after process exit, including output over one pipe buffer.
                    drainAvailable(process.inputStream, stdout, buffer, process.inputStream.available())
                    drainAvailable(process.errorStream, stderr, buffer, process.errorStream.available())
                    return@withContext ShellResult(process.exitValue(), stdout.toString("UTF-8"), stderr.toString("UTF-8"))
                }
                val remaining = timeoutMs - (System.nanoTime() - startedAt) / 1_000_000L
                if (remaining <= 0L) {
                    return@withContext ShellResult(124, stdout.toString("UTF-8"), "命令执行超时\n${stderr.toString("UTF-8")}".trim())
                }
                // Suspending checks avoid uninterruptible waitFor/readText workers. Both pipes
                // are drained together so a full stderr pipe cannot stall a stdout reader.
                delay(minOf(if (outputBytes > 0) 1L else 50L, remaining))
            }
            @Suppress("UNREACHABLE_CODE")
            error("Process loop ended unexpectedly")
        } finally {
            if (process.isAlive) process.destroyForcibly()
            runCatching { process.inputStream.close() }
            runCatching { process.errorStream.close() }
            runCatching { process.outputStream.close() }
        }
    }

private fun drainAvailable(stream: InputStream, target: ByteArrayOutputStream, buffer: ByteArray, maxBytes: Int = 65_536): Int {
    // A bounded pass prevents an endlessly verbose process from starving cancellation/the deadline.
    var readBytes = 0
    while (readBytes < maxBytes) {
        val available = stream.available()
        if (available <= 0) break
        val count = stream.read(buffer, 0, minOf(available, buffer.size, maxBytes - readBytes))
        if (count <= 0) break
        target.write(buffer, 0, count)
        readBytes += count
    }
    return readBytes
}
