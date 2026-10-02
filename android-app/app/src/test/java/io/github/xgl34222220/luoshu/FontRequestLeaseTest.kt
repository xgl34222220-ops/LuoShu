package io.github.xgl34222220.luoshu

import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.*
import org.junit.Test

/** End-to-end JVM pipe lifecycle against the actual finite request helper, not detached-task mocks. */
class FontRequestLeaseTest {
    private val helper: File
        get() = generateSequence(File(System.getProperty("user.dir"))) { it.parentFile }
            .map { File(it, "common/font_request_scope.py") }.first { it.isFile }

    private fun command(directory: File): List<String> {
        val worker = """
            import os, signal, sys, time
            def record():
                fields=open('/proc/self/stat').read().rsplit(') ',1)[1].split()
                with open(sys.argv[1], 'a') as stream: stream.write(str(os.getpid())+' '+fields[19]+'\n')
            record()
            if os.fork()==0:
                os.setsid()
                if os.fork()>0: os._exit(0)
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                record()
                while True: time.sleep(.05)
            while True: time.sleep(.05)
        """.trimIndent()
        return listOf("python3", helper.path, "--scope-dir", directory.resolve("scope").path,
            "--timeout", "30", "--", "python3", "-c", worker, directory.resolve("workers").path)
    }

    private fun assertReaped(directory: File) {
        val rows = directory.resolve("workers").readLines()
        assertTrue(rows.size >= 2)
        rows.forEach { row ->
            val (pid, start) = row.split(' ')
            val stat = File("/proc/$pid/stat")
            val same = runCatching { stat.readText().substringAfterLast(") ").split(' ')[19] == start }.getOrDefault(false)
            assertFalse("Owned process still exists: $row", same)
        }
        assertTrue(directory.resolve("scope").listFiles().orEmpty().isEmpty())
    }

    @Test
    fun coroutineCancellationClosesLeaseAndWaitsForDescendantReaping() = runBlocking {
        val directory = Files.createTempDirectory("luoshu-request-cancel").toFile()
        try {
            val job = launch { executeProcess(command(directory), 30_000L, keepStdinOpen = true, cleanupGraceMs = 6_000L) }
            withTimeout(8_000L) {
                while (!directory.resolve("workers").exists() || directory.resolve("workers").readLines().size < 2) delay(10L)
                job.cancelAndJoin()
            }
            assertTrue(job.isCancelled)
            assertReaped(directory)
        } finally { directory.deleteRecursively() }
    }

    @Test
    fun callerTimeoutClosesLeaseRatherThanOnlyKillingItsShell() = runBlocking {
        val directory = Files.createTempDirectory("luoshu-request-timeout").toFile()
        try {
            val result = withTimeout(8_000L) {
                executeProcess(command(directory), 500L, keepStdinOpen = true, cleanupGraceMs = 6_000L)
            }
            assertEquals(124, result.code)
            assertReaped(directory)
        } finally { directory.deleteRecursively() }
    }
}
