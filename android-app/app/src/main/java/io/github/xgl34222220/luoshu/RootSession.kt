package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.IOException
import java.io.InputStream
import java.util.UUID

/**
 * One long-lived root shell shared by all App requests.
 *
 * Every request still reaches the shell as the exact command executeScopedRequest built (task_scope
 * request-run/request-cancel by token), so ownership and cleanup semantics are unchanged; only the
 * per-request `su -c` fork is gone. Requests run strictly one at a time through [mutex]. A request
 * that cannot get the session within [queueWaitMs] (e.g. behind a long stock scan) falls back to the
 * previous one-shot `su -c` path instead of stalling short status reads.
 *
 * Timeout, cancellation or a broken pipe destroys the session; the next request rebuilds it. The
 * session is closed after [idleCloseMs] without requests and on [close].
 */
internal class RootSession(
    private val processFactory: () -> Process = { ProcessBuilder("su").redirectErrorStream(false).start() },
    private val oneShot: suspend (List<String>, Long) -> ShellResult = ::executeProcess,
    private val queueWaitMs: Long = ROOT_SESSION_QUEUE_WAIT_MS,
    private val idleCloseMs: Long = ROOT_SESSION_IDLE_CLOSE_MS,
) {
    private val mutex = Mutex()
    private val idleScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val lock = Any()
    private var process: Process? = null
    private var idleJob: Job? = null
    private var generation = 0L

    /** Number of shell processes started so far (for tests/diagnostics). */
    val startedSessions: Long get() = synchronized(lock) { generation }

    /** Same contract as executeProcess(["su", "-c", command]). */
    suspend fun execute(command: String, timeoutMs: Long): ShellResult {
        require(timeoutMs > 0L) { "Request timeout must be positive" }
        val acquired = withTimeoutOrNull(queueWaitMs.coerceAtLeast(1L)) { mutex.lock(); true } ?: false
        if (!acquired) return oneShot(listOf("su", "-c", command), timeoutMs)
        try {
            cancelIdleClose()
            return runLocked(command, timeoutMs)
        } finally {
            scheduleIdleClose()
            mutex.unlock()
        }
    }

    /** Closes the shell now if idle, otherwise right after the running request. */
    fun close() {
        if (mutex.tryLock()) {
            try {
                destroy()
            } finally {
                mutex.unlock()
            }
        } else {
            synchronized(lock) { idleJob?.cancel(); idleJob = null }
            idleScope.launch {
                mutex.lock()
                try { destroy() } finally { mutex.unlock() }
            }
        }
    }

    internal val isOpen: Boolean get() = synchronized(lock) { process?.isAlive == true }

    private suspend fun runLocked(command: String, timeoutMs: Long): ShellResult = withContext(Dispatchers.IO) {
        currentCoroutineContext().ensureActive()
        val shell = obtain()
        val nonce = UUID.randomUUID().toString().replace("-", "")
        val marker = "__LUOSHU_END_${nonce}__"
        val stdout = GrowingBuffer()
        val stderr = GrowingBuffer()
        val buffer = ByteArray(8_192)
        val startedAt = System.nanoTime()
        var completed = false
        try {
            // Output a previous request's detached descendant wrote after its marker is not ours.
            discardAvailable(shell.inputStream, buffer)
            discardAvailable(shell.errorStream, buffer)
            val script = rootSessionScript(command, marker)
            try {
                shell.outputStream.write(script.toByteArray(Charsets.UTF_8))
                shell.outputStream.flush()
            } catch (error: IOException) {
                // su refused or exited before reading: report it like the old one-shot request.
                if (!awaitExit(shell, 500L)) throw error
            }
            var idleWaitMs = IDLE_WAIT_MIN_MS
            while (true) {
                currentCoroutineContext().ensureActive()
                val read = drainInto(shell.inputStream, stdout, buffer) + drainInto(shell.errorStream, stderr, buffer)
                val parsed = parseRootSessionOutput(stdout, stderr, marker)
                if (parsed != null) {
                    completed = true
                    return@withContext parsed
                }
                if (!shell.isAlive) {
                    drainInto(shell.inputStream, stdout, buffer, Int.MAX_VALUE)
                    drainInto(shell.errorStream, stderr, buffer, Int.MAX_VALUE)
                    parseRootSessionOutput(stdout, stderr, marker)?.let {
                        completed = true
                        return@withContext it
                    }
                    val exit = shell.exitValue().takeIf { it != 0 } ?: 1
                    val message = stderr.text().ifBlank { "Root 会话意外结束" }
                    return@withContext ShellResult(exit, stdout.text(), message)
                }
                val remaining = timeoutMs - (System.nanoTime() - startedAt) / 1_000_000L
                if (remaining <= 0L) {
                    return@withContext ShellResult(124, stdout.text(), "命令执行超时\n${stderr.text()}".trim())
                }
                idleWaitMs = if (read > 0) IDLE_WAIT_MIN_MS else minOf(idleWaitMs * 2L, IDLE_WAIT_MAX_MS)
                delay(minOf(if (read > 0) 1L else idleWaitMs, remaining))
            }
            @Suppress("UNREACHABLE_CODE")
            error("Root session loop ended unexpectedly")
        } finally {
            // Timeout, cancellation, pipe failure or shell death: the session state is unknown.
            if (!completed) destroy()
        }
    }

    private fun obtain(): Process = synchronized(lock) {
        process?.takeIf { it.isAlive }?.let { return it }
        process?.let { destroyProcess(it) }
        val started = processFactory()
        generation += 1
        process = started
        started
    }

    private fun destroy() {
        val current = synchronized(lock) {
            idleJob?.cancel()
            idleJob = null
            process.also { process = null }
        } ?: return
        destroyProcess(current)
    }

    private fun destroyProcess(target: Process) {
        runCatching {
            target.outputStream.write("exit\n".toByteArray())
            target.outputStream.flush()
        }
        runCatching { target.outputStream.close() }
        if (target.isAlive) target.destroyForcibly()
        runCatching { target.inputStream.close() }
        runCatching { target.errorStream.close() }
    }

    private fun cancelIdleClose() = synchronized(lock) {
        idleJob?.cancel()
        idleJob = null
    }

    private fun scheduleIdleClose() {
        if (idleCloseMs <= 0L) return
        synchronized(lock) {
            if (process == null) return
            idleJob?.cancel()
            idleJob = idleScope.launch {
                delay(idleCloseMs)
                if (mutex.tryLock()) {
                    try { destroy() } finally { mutex.unlock() }
                }
            }
        }
    }

    private suspend fun awaitExit(target: Process, timeoutMs: Long): Boolean {
        val deadline = System.nanoTime() + timeoutMs * 1_000_000L
        while (target.isAlive && System.nanoTime() < deadline) delay(10L)
        return !target.isAlive
    }
}

internal const val ROOT_SESSION_QUEUE_WAIT_MS = 1_500L
internal const val ROOT_SESSION_IDLE_CLOSE_MS = 45_000L
private const val MARKER_TAIL_WINDOW = 4_096
private const val IDLE_WAIT_MIN_MS = 4L
private const val IDLE_WAIT_MAX_MS = 50L

/**
 * The command runs in a child `sh -c` with stdin from /dev/null: it cannot read later requests
 * from the session pipe, and `exit`/`set -e` inside it cannot end the persistent shell.
 */
internal fun rootSessionScript(command: String, marker: String): String =
    "sh -c ${RootShell.quote(command)} </dev/null; __luoshu_rc=\$?; " +
        "printf '\\n%s:%s\\n' '$marker' \"\$__luoshu_rc\"; printf '\\n%s\\n' '$marker' >&2\n"

internal class GrowingBuffer {
    private var bytes = ByteArray(8_192)
    var size = 0
        private set

    fun write(source: ByteArray, count: Int) {
        if (size + count > bytes.size) bytes = bytes.copyOf(maxOf(bytes.size * 2, size + count))
        System.arraycopy(source, 0, bytes, size, count)
        size += count
    }

    fun indexOf(pattern: ByteArray, from: Int): Int {
        var start = from.coerceAtLeast(0)
        val last = size - pattern.size
        while (start <= last) {
            var match = true
            for (offset in pattern.indices) {
                if (bytes[start + offset] != pattern[offset]) { match = false; break }
            }
            if (match) return start
            start += 1
        }
        return -1
    }

    fun text(end: Int = size): String = String(bytes, 0, end, Charsets.UTF_8)
    fun byteAt(index: Int): Byte = bytes[index]
}

/** Returns the request result once both end markers are present; null while it is still running. */
internal fun parseRootSessionOutput(stdout: GrowingBuffer, stderr: GrowingBuffer, marker: String): ShellResult? {
    val outMarker = "\n$marker:".toByteArray(Charsets.UTF_8)
    val errMarker = "\n$marker\n".toByteArray(Charsets.UTF_8)
    // Markers are the last thing each stream receives; only the tail needs scanning. The window
    // tolerates a little late output from a detached descendant that kept the pipe.
    val outIndex = stdout.indexOf(outMarker, stdout.size - outMarker.size - MARKER_TAIL_WINDOW)
    if (outIndex < 0) return null
    val errIndex = stderr.indexOf(errMarker, stderr.size - errMarker.size - MARKER_TAIL_WINDOW)
    if (errIndex < 0) return null
    var cursor = outIndex + outMarker.size
    val digits = StringBuilder()
    while (cursor < stdout.size && stdout.byteAt(cursor) != '\n'.code.toByte()) {
        digits.append(stdout.byteAt(cursor).toInt().toChar())
        cursor += 1
    }
    if (cursor >= stdout.size) return null
    val code = digits.toString().trim().toIntOrNull() ?: return null
    return ShellResult(code, stdout.text(outIndex), stderr.text(errIndex))
}

private fun drainInto(stream: InputStream, target: GrowingBuffer, buffer: ByteArray, maxBytes: Int = 65_536): Int {
    var readBytes = 0
    while (readBytes < maxBytes) {
        val available = runCatching { stream.available() }.getOrDefault(0)
        if (available <= 0) break
        val count = stream.read(buffer, 0, minOf(available, buffer.size, maxBytes - readBytes))
        if (count <= 0) break
        target.write(buffer, count)
        readBytes += count
    }
    return readBytes
}

private fun discardAvailable(stream: InputStream, buffer: ByteArray) {
    while (true) {
        val available = runCatching { stream.available() }.getOrDefault(0)
        if (available <= 0) return
        if (stream.read(buffer, 0, minOf(available, buffer.size)) <= 0) return
    }
}
