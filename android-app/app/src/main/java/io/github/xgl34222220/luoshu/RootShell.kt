package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
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
            process = ProcessBuilder("su", "-c", command)
                .redirectErrorStream(false)
                .start()

            coroutineScope {
                val stdout = async(Dispatchers.IO) {
                    process.inputStream.bufferedReader().use { it.readText() }
                }
                val stderr = async(Dispatchers.IO) {
                    process.errorStream.bufferedReader().use { it.readText() }
                }

                val finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
                if (!finished) {
                    process.destroyForcibly()
                    ShellResult(124, stdout.await(), "命令执行超时\n${stderr.await()}".trim())
                } else {
                    ShellResult(process.exitValue(), stdout.await(), stderr.await())
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
            ShellResult(127, "", error.message ?: error.javaClass.simpleName)
        } finally {
            if (!currentCoroutineContext().isActive) process?.destroyForcibly()
        }
    }

    fun quote(value: String): String = "'" + value.replace("'", "'\\''") + "'"
}
