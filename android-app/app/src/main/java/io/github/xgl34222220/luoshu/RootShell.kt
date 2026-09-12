package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream

internal data class ShellResult(
    val code: Int,
    val stdout: String,
    val stderr: String,
)

internal object RootShell {
    suspend fun exec(command: String, timeoutMs: Long = 600_000L): ShellResult = withContext(Dispatchers.IO) {
        try {
            executeProcess(listOf("su", "-c", command), timeoutMs)
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
                return@withContext ShellResult(75, "", "Root 输出暂时中断，请重试")
            }
            val message = if (
                error is IOException &&
                (raw.contains("Cannot run program \"su\"") || raw.contains("No such file or directory"))
            ) {
                "未找到 Root 命令 su。请先在 Root 管理器中完成待生效变更并完整重启，然后为洛书授予 Root 权限。"
            } else {
                raw.ifBlank { error.javaClass.simpleName }
            }
            ShellResult(127, "", message)
        }
    }

    fun quote(value: String): String = "'" + value.replace("'", "'\\''") + "'"
}

/** Owns only the request process. Module workers are detached by app_bridge.sh. */
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
