package io.github.xgl34222220.luoshu

import java.nio.file.Files
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Uses plain `sh` as the long-lived shell; the protocol is identical to the su session. */
class RootSessionTest {
    private fun session(
        oneShot: suspend (List<String>, Long) -> ShellResult = { _, _ -> error("unexpected one-shot fallback") },
        queueWaitMs: Long = 30_000L,
        idleCloseMs: Long = 0L,
    ) = RootSession(
        processFactory = { ProcessBuilder("sh").redirectErrorStream(false).start() },
        oneShot = oneShot,
        queueWaitMs = queueWaitMs,
        idleCloseMs = idleCloseMs,
    )

    @Test
    fun reusesOneShellForManyRequestsAndKeepsExitCodesAndStreamsExact() = runBlocking {
        val shell = session()
        try {
            val first = shell.execute("printf '字体正常'; printf 'warning' >&2; exit 7", 5_000L)
            assertEquals(7, first.code)
            assertEquals("字体正常", first.stdout)
            assertEquals("warning", first.stderr)
            val second = shell.execute("printf 'line\\n'; printf 'err\\n' >&2", 5_000L)
            assertEquals(0, second.code)
            assertEquals("line\n", second.stdout)
            assertEquals("err\n", second.stderr)
            val empty = shell.execute("true", 5_000L)
            assertEquals(ShellResult(0, "", ""), empty)
            assertEquals(1L, shell.startedSessions)
        } finally {
            shell.close()
        }
    }

    @Test
    fun exitAndShellOptionsInsideARequestCannotEndOrPolluteTheSession() = runBlocking {
        val shell = session()
        try {
            assertEquals(1, shell.execute("set -e; cd /; FOO=leak; false; exit 0", 5_000L).code)
            assertEquals(42, shell.execute("exit 42", 5_000L).code)
            val env = shell.execute("printf '%s|%s' \"\${FOO:-unset}\" \"\$(pwd)\"", 5_000L)
            assertEquals("unset|" + java.io.File(".").canonicalPath, env.stdout)
            assertEquals(1L, shell.startedSessions)
        } finally {
            shell.close()
        }
    }

    @Test
    fun requestsCannotReadTheSessionPipeAsStdin() = runBlocking {
        val shell = session()
        try {
            val result = withTimeout(3_000L) { shell.execute("cat; printf done", 2_000L) }
            assertEquals(0, result.code)
            assertEquals("done", result.stdout)
            assertEquals("next", shell.execute("printf next", 2_000L).stdout)
        } finally {
            shell.close()
        }
    }

    @Test
    fun largeOutputOnBothStreamsDoesNotDeadlock() = runBlocking {
        val shell = session()
        try {
            val result = withTimeout(8_000L) {
                shell.execute("head -c 262144 /dev/zero | tr '\\0' a; head -c 262144 /dev/zero | tr '\\0' b >&2", 6_000L)
            }
            assertEquals(0, result.code)
            assertEquals(262_144, result.stdout.length)
            assertEquals(262_144, result.stderr.length)
        } finally {
            shell.close()
        }
    }

    @Test
    fun concurrentRequestsAreSerialisedThroughTheSingleSession() = runBlocking {
        val directory = Files.createTempDirectory("luoshu-session-serial").toFile()
        val shell = session()
        try {
            val log = directory.resolve("log")
            val results = (1..6).map { index ->
                async {
                    shell.execute(
                        "printf 'start$index\\n' >> ${RootShell.quote(log.path)}; sleep 0.05; " +
                            "printf 'end$index\\n' >> ${RootShell.quote(log.path)}; printf $index",
                        5_000L,
                    )
                }
            }.awaitAll()
            assertEquals((1..6).map { it.toString() }, results.map { it.stdout })
            val lines = log.readLines()
            // Every start is immediately followed by its own end: no interleaving.
            lines.chunked(2).forEach { (start, end) -> assertEquals(start.removePrefix("start"), end.removePrefix("end")) }
            assertEquals(1L, shell.startedSessions)
        } finally {
            shell.close()
            directory.deleteRecursively()
        }
    }

    @Test
    fun timeoutReturnsPartialOutputDestroysTheSessionAndTheNextRequestRebuildsIt() = runBlocking {
        val shell = session()
        try {
            val timedOut = withTimeout(3_000L) { shell.execute("printf started; sleep 30", 200L) }
            assertEquals(124, timedOut.code)
            assertEquals("started", timedOut.stdout)
            assertTrue(timedOut.stderr.contains("超时"))
            assertFalse(shell.isOpen)
            val next = shell.execute("printf ok", 2_000L)
            assertEquals("ok", next.stdout)
            assertEquals(2L, shell.startedSessions)
        } finally {
            shell.close()
        }
    }

    @Test
    fun cancellationDestroysTheSessionPromptly() = runBlocking {
        val shell = session()
        try {
            val started = CompletableDeferred<Unit>()
            val job = launch {
                started.complete(Unit)
                shell.execute("sleep 30", 30_000L)
            }
            withTimeout(3_000L) {
                started.await()
                delay(100L)
                job.cancelAndJoin()
            }
            assertTrue(job.isCancelled)
            assertFalse(shell.isOpen)
            assertEquals("again", shell.execute("printf again", 2_000L).stdout)
        } finally {
            shell.close()
        }
    }

    @Test
    fun aDeadShellIsReportedAndRebuiltOnTheNextRequest() = runBlocking {
        val shell = session()
        try {
            // Killing the shell itself (not the child sh -c) simulates a dropped su connection.
            val dead = withTimeout(3_000L) { shell.execute("kill -9 \$PPID; sleep 5", 5_000L) }
            assertTrue(dead.code != 0)
            assertEquals("alive", shell.execute("printf alive", 2_000L).stdout)
            assertEquals(2L, shell.startedSessions)
        } finally {
            shell.close()
        }
    }

    @Test
    fun aBusySessionFallsBackToAOneShotRequestInsteadOfBlockingShortReads() = runBlocking {
        val fallbacks = AtomicInteger()
        val shell = session(
            oneShot = { command, timeout ->
                fallbacks.incrementAndGet()
                assertEquals(listOf("su", "-c", "printf status"), command)
                assertEquals(2_000L, timeout)
                ShellResult(0, "status", "")
            },
            queueWaitMs = 100L,
        )
        try {
            val long = async { shell.execute("sleep 1; printf long", 5_000L) }
            delay(150L)
            val quick = withTimeout(1_000L) { shell.execute("printf status", 2_000L) }
            assertEquals("status", quick.stdout)
            assertEquals(1, fallbacks.get())
            assertEquals("long", long.await().stdout)
        } finally {
            shell.close()
        }
    }

    @Test
    fun idleSessionClosesItselfAndCloseIsIdempotent() = runBlocking {
        val shell = session(idleCloseMs = 150L)
        try {
            shell.execute("true", 2_000L)
            assertTrue(shell.isOpen)
            withTimeout(3_000L) { while (shell.isOpen) delay(20L) }
            shell.close()
            shell.close()
            assertEquals("reopened", shell.execute("printf reopened", 2_000L).stdout)
        } finally {
            shell.close()
        }
    }

    @Test
    fun theScopedRequestRunsThroughTheSessionWithTheSameTaskScopeCommand() = runBlocking {
        val commands = mutableListOf<List<String>>()
        val result = executeScopedRequest("printf ok", 5_000L, token = "session-owned", executor = { command, timeout ->
            commands += command
            assertEquals(5_000L, timeout)
            ShellResult(0, "ok", "")
        })
        assertEquals("ok", result.stdout)
        assertEquals("su", commands.single()[0])
        assertEquals("-c", commands.single()[1])
        assertTrue(commands.single()[2].contains("request-run 'session-owned' 5 -- sh -c 'printf ok'"))
    }

    @Test
    fun markerParserIgnoresLookalikeOutputAndWaitsForBothStreams() {
        val marker = "__LUOSHU_END_abc__"
        val stdout = GrowingBuffer()
        val stderr = GrowingBuffer()
        fun GrowingBuffer.add(text: String) = text.toByteArray().let { write(it, it.size) }
        stdout.add("payload __LUOSHU_END_other__:0\n")
        assertEquals(null, parseRootSessionOutput(stdout, stderr, marker))
        stdout.add("\n$marker:5\n")
        assertEquals(null, parseRootSessionOutput(stdout, stderr, marker))
        stderr.add("oops\n\n$marker\n")
        val parsed = parseRootSessionOutput(stdout, stderr, marker)
        assertEquals(ShellResult(5, "payload __LUOSHU_END_other__:0\n", "oops\n"), parsed)
    }
}
