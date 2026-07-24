package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.concurrent.TimeUnit

internal data class ShellResult(
    val code: Int,
    val stdout: String,
    val stderr: String,
)

internal object RootShell {
    suspend fun exec(command: String, timeoutMs: Long = 600_000L): ShellResult = withContext(Dispatchers.IO) {
        var process: Process? = null
        try {
            val activeProcess = ProcessBuilder("su", "-c", command)
                .redirectErrorStream(false)
                .start()
            process = activeProcess

            coroutineScope {
                val stdout = async(Dispatchers.IO) {
                    activeProcess.inputStream.bufferedReader().use { it.readText() }
                }
                val stderr = async(Dispatchers.IO) {
                    activeProcess.errorStream.bufferedReader().use { it.readText() }
                }

                val finished = activeProcess.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
                if (!finished) {
                    activeProcess.destroyForcibly()
                    ShellResult(124, stdout.await(), "命令执行超时\n${stderr.await()}".trim())
                } else {
                    ShellResult(activeProcess.exitValue(), stdout.await(), stderr.await())
                }
            }
        } catch (cancelled: CancellationException) {
            process?.destroyForcibly()
            throw cancelled
        } catch (interrupted: InterruptedException) {
            process?.destroyForcibly()
            throw CancellationException("Command cancelled").also { it.initCause(interrupted) }
        } catch (error: Throwable) {
            process?.destroyForcibly()
            val raw = error.message.orEmpty()
            val message = if (
                error is IOException &&
                (raw.contains("Cannot run program \"su\"") || raw.contains("No such file or directory"))
            ) {
                "未找到 Root 命令 su。请先在 Root 管理器中完成待生效变更并完整重启，然后为洛书授予 Root 权限。"
            } else {
                raw.ifBlank { error.javaClass.simpleName }
            }
            ShellResult(127, "", message)
        } finally {
            if (!currentCoroutineContext().isActive) process?.destroyForcibly()
        }
    }

    fun quote(value: String): String = "'" + value.replace("'", "'\\''") + "'"
}
