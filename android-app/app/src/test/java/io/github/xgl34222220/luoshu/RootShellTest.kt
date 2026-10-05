package io.github.xgl34222220.luoshu

import java.nio.file.Files
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withContext
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class RootShellTest {
    @Test
    fun preservesExitCodeAndBothOutputStreams() = runBlocking {
        val result = executeProcess(listOf("sh", "-c", "printf '字体正常'; printf 'warning' >&2; exit 7"), 2_000L)
        assertEquals(7, result.code)
        assertEquals("字体正常", result.stdout)
        assertEquals("warning", result.stderr)
    }

    @Test
    fun drainsLargeStdoutAndStderrWithoutAFullPipeDeadlock() = runBlocking {
        val result = withTimeout(5_000L) {
            executeProcess(
                listOf("sh", "-c", "head -c 262144 /dev/zero; head -c 262144 /dev/zero >&2"),
                4_000L,
            )
        }
        assertEquals(0, result.code)
        assertEquals(262_144, result.stdout.length)
        assertEquals(262_144, result.stderr.length)
    }

    @Test
    fun closesStdinSoNonInteractiveRequestsCanFinish() = runBlocking {
        val result = executeProcess(listOf("sh", "-c", "cat; printf done"), 2_000L)
        assertEquals(0, result.code)
        assertEquals("done", result.stdout)
    }

    @Test
    fun cancellationReapsTheRequestInsteadOfWaitingForItsTimeout() = runBlocking {
        val directory = Files.createTempDirectory("luoshu-cancel").toFile()
        val pidFile = directory.resolve("request.pid")
        var procPid = ""
        var job: Job? = null
        try {
            val fixture = "import os,sys,time; open(sys.argv[1],'w').write(os.readlink('/proc/self')); time.sleep(30)"
            val requestJob = launch {
                executeProcess(listOf("sh", "-c", "exec python3 -c ${RootShell.quote(fixture)} ${RootShell.quote(pidFile.path)}"), 30_000L)
            }
            job = requestJob
            withTimeout(3_000L) {
                while (!pidFile.exists() || pidFile.length() == 0L) delay(10L)
                procPid = pidFile.readText()
                assertTrue(java.io.File("/proc/$procPid").exists())
                requestJob.cancelAndJoin()
                while (java.io.File("/proc/$procPid").exists()) delay(10L)
            }
            assertTrue(requestJob.isCancelled)
            assertFalse(java.io.File("/proc/$procPid").exists())
        } finally {
            withContext(NonCancellable) { job?.cancelAndJoin() }
            directory.deleteRecursively()
        }
    }

    @Test
    fun timeoutReturnsPartialOutputAndTerminatesTheRequest() = runBlocking {
        val directory = Files.createTempDirectory("luoshu-timeout").toFile()
        val pidFile = directory.resolve("request.pid")
        try {
            val fixture = "import os,sys,time; open(sys.argv[1],'w').write(os.readlink('/proc/self')); print('started',end='',flush=True); time.sleep(30)"
            val result = withTimeout(3_000L) {
                executeProcess(
                    listOf("sh", "-c", "exec python3 -c ${RootShell.quote(fixture)} ${RootShell.quote(pidFile.path)}"),
                    200L,
                )
            }
            assertEquals(124, result.code)
            assertEquals("started", result.stdout)
            assertTrue(result.stderr.contains("超时"))
            val procPid = pidFile.readText()
            withTimeout(2_000L) {
                while (java.io.File("/proc/$procPid").exists()) delay(10L)
            }
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun cancellingARequestDoesNotKillItsDetachedFontWorker() = runBlocking {
        val directory = Files.createTempDirectory("luoshu-detached").toFile()
        val ready = directory.resolve("ready")
        val finished = directory.resolve("finished")
        try {
            val workerCommand = "sleep 0.3; printf done > ${RootShell.quote(finished.path)}"
            val job = launch {
                executeProcess(
                    listOf("sh", "-c", "sh -c ${RootShell.quote(workerCommand)} </dev/null >/dev/null 2>&1 & printf ready > ${RootShell.quote(ready.path)}; exec sleep 30"),
                    30_000L,
                )
            }
            withTimeout(3_000L) {
                while (!ready.exists()) delay(10L)
                job.cancelAndJoin()
                while (!finished.exists() || finished.length() == 0L) delay(10L)
            }
            assertEquals("done", finished.readText())
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun aDescendantHoldingThePipeDoesNotExtendTheRequestLifetime() = runBlocking {
        val result = withTimeout(1_500L) {
            executeProcess(listOf("sh", "-c", "sleep 2 & printf submitted"), 5_000L)
        }
        assertEquals(0, result.code)
        assertEquals("submitted", result.stdout)
    }

    @Test
    fun scopedCancellationWaitsForCleanupUsingTheExactTokenOutsideTheCancelledJob() = runBlocking {
        val started = CompletableDeferred<Unit>()
        val cleanupStarted = CompletableDeferred<Unit>()
        val releaseCleanup = CompletableDeferred<Unit>()
        val commands = mutableListOf<List<String>>()
        val job = launch {
            executeScopedRequest("printf '字体'; sleep 30", 30_000L, token = "request-owned", executor = { command, _ ->
                synchronized(commands) { commands += command }
                if (command.last().contains("request-run")) {
                    started.complete(Unit)
                    delay(30_000L)
                    ShellResult(0, "", "")
                } else {
                    cleanupStarted.complete(Unit)
                    releaseCleanup.await()
                    ShellResult(0, "{\"status\":\"ok\",\"data\":{\"token\":\"request-owned\",\"cleaned\":true}}", "")
                }
            })
        }
        withTimeout(3_000L) {
            started.await()
            job.cancel()
            cleanupStarted.await()
            assertFalse(job.isCompleted)
            assertTrue(commands.last().last().endsWith("request-cancel 'request-owned'"))
            releaseCleanup.complete(Unit)
            job.join()
        }
        assertTrue(job.isCancelled)
        assertEquals(2, commands.size)
    }

    @Test
    fun scopedTimeoutCannotAcceptAnotherRequestsCleanupReceipt() = runBlocking {
        val commands = mutableListOf<List<String>>()
        val result = executeScopedRequest("sleep 30", 101L, token = "wanted", executor = { command, timeout ->
            commands += command
            if (command.last().contains("request-run")) {
                assertEquals(101L, timeout)
                assertTrue(command.last().contains("request-run 'wanted' 1 --"))
                ShellResult(124, "partial", "timeout")
            } else {
                ShellResult(0, "{\"status\":\"ok\",\"data\":{\"token\":\"unrelated\",\"cleaned\":true}}", "")
            }
        })
        assertEquals(124, result.code)
        assertEquals("partial", result.stdout)
        assertFalse(result.cleanupVerified)
        assertTrue(result.stderr.contains("清理尚未确认"))
        assertEquals(2, commands.size)
    }

    @Test
    fun scopedPipeFailureStillRequestsCleanupForPossibleSpawnedChildren() = runBlocking {
        val failure = java.io.IOException("pipe broke after spawn")
        var cleaned = false
        try {
            executeScopedRequest("spawn", 1_000L, token = "broken-pipe", executor = { command, _ ->
                if (command.last().contains("request-run")) throw failure
                cleaned = true
                ShellResult(0, "{\"status\":\"ok\",\"data\":{\"token\":\"broken-pipe\",\"cleaned\":true}}", "")
            })
            error("Expected pipe failure")
        } catch (caught: java.io.IOException) {
            assertSame(failure, caught)
        }
        assertTrue(cleaned)
    }

    @Test
    fun supervisorResidueIsRetriedAndCannotBeReportedAsAnOrdinaryCommandFailure() = runBlocking {
        var cleanupCalls = 0
        val result = executeScopedRequest("font-builder", 1_000L, token = "residue", executor = { command, _ ->
            if (command.last().contains("request-run")) {
                ShellResult(125, "", "owned child remains")
            } else {
                cleanupCalls += 1
                ShellResult(125, "{\"status\":\"error\",\"data\":{\"token\":\"residue\",\"cleaned\":false}}", "cleanup-failed")
            }
        })
        assertEquals(1, cleanupCalls)
        assertFalse(result.cleanupVerified)
        try {
            result.requireCleaned()
            error("Must keep cleanup pending")
        } catch (failure: OwnedTaskCleanupFailure) {
            assertTrue(failure.cleanupUnconfirmed())
        }
    }

    @Test
    fun ownedFontCancellationWaitsForWorkerCleanupBeforePublishingCompletion() = runBlocking {
        val started = CompletableDeferred<Unit>()
        val cleanupStarted = CompletableDeferred<Unit>()
        val releaseCleanup = CompletableDeferred<Unit>()
        var published = false
        val job = launch {
            awaitOwnedFontTask(
                taskId = "font-42", cancelCommand = "font-switch-cancel 'font-42'",
                onCleanup = { cleaned, _ -> assertTrue(cleaned); published = true },
                executor = { command, _ ->
                    assertEquals("font-switch-cancel 'font-42'", command)
                    cleanupStarted.complete(Unit)
                    releaseCleanup.await()
                    ShellResult(0, "{\"status\":\"ok\",\"data\":{\"task\":\"font-42\",\"cleaned\":true}}", "")
                },
            ) {
                started.complete(Unit)
                delay(30_000L)
            }
        }
        withTimeout(3_000L) {
            started.await()
            job.cancel()
            cleanupStarted.await()
            assertFalse(published)
            assertFalse(job.isCompleted)
            releaseCleanup.complete(Unit)
            job.join()
        }
        assertTrue(published)
        assertTrue(job.isCancelled)
    }

    @Test
    fun lostTaskObserverRequestsOnlyItsOwnTaskAndKeepsCleanupFailureVisible() = runBlocking {
        val failure = IllegalStateException("observer timed out")
        var cleanupVerified: Boolean? = null
        try {
            awaitOwnedFontTask(
                taskId = "old-task", cancelCommand = "font-mix-cancel 'old-task'",
                onCleanup = { cleaned, _ -> cleanupVerified = cleaned },
                executor = { command, _ ->
                    assertEquals("font-mix-cancel 'old-task'", command)
                    ShellResult(0, "{\"status\":\"ok\",\"data\":{\"task\":\"new-task\",\"cleaned\":true}}", "")
                },
            ) { throw failure }
            error("Expected observer failure")
        } catch (caught: IllegalStateException) {
            assertSame(failure, caught)
            assertTrue(caught.cleanupUnconfirmed())
        }
        assertEquals(false, cleanupVerified)
    }

    @Test
    fun completedFontTaskDoesNotCancelAnotherTask() = runBlocking {
        val value = awaitOwnedFontTask(
            taskId = "finished", cancelCommand = "font-switch-cancel 'finished'",
            onCleanup = { _, _ -> error("Successful worker was already reaped by the backend") },
            executor = { _, _ -> error("Must not send cancel after confirmed success") },
        ) { "ready-next-boot" }
        assertEquals("ready-next-boot", value)
    }

    @Test
    fun cleanupReceiptRequiresSuccessAndTheVerifiedOwnerIdentity() {
        assertFalse(cleanupConfirmed(ShellResult(0, "{\"status\":\"error\",\"data\":{\"token\":\"mine\",\"cleaned\":true}}", ""), "token", "mine"))
        assertFalse(cleanupConfirmed(ShellResult(0, "not json", ""), "token", "mine"))
        assertFalse(cleanupConfirmed(ShellResult(1, "{\"status\":\"ok\",\"data\":{\"token\":\"mine\",\"cleaned\":true}}", ""), "token", "mine"))
        assertTrue(cleanupConfirmed(ShellResult(0, "{\"status\":\"ok\",\"data\":{\"token\":\"mine\",\"cleaned\":true}}", ""), "token", "mine"))
    }

    @Test
    fun scopedAppCancellationReapsAnEscapedWorkerAndPreservesAnUnrelatedProcess() = runBlocking {
        val repository = sequenceOf(
            System.getProperty("luoshu.repo")?.let { java.io.File(it) },
            java.io.File("."), java.io.File(".."), java.io.File("../.."), java.io.File("../../.."),
        ).filterNotNull().first { it.resolve("common/task_scope.sh").isFile }
        val directory = Files.createTempDirectory("luoshu-owned-request").toFile()
        val module = directory.resolve("module")
        val common = module.resolve("common").apply { mkdirs() }
        listOf("task_scope.sh", "task_scope.py").forEach { name ->
            repository.resolve("common/$name").copyTo(common.resolve(name))
        }
        val childPidFile = directory.resolve("escaped.pid")
        val tasks = directory.resolve("tasks")
        val temporary = directory.resolve("tmp")
        val sentinel = ProcessBuilder("sleep", "30").start()
        var childProcPid = ""
        var job: Job? = null
        val fixture = "import os,signal,sys,time; " +
            "child=os.fork(); " +
            "os.setsid() if child==0 else None; " +
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); " +
            "open(sys.argv[1],'w').write(os.readlink('/proc/self')) if child==0 else None; " +
            "time.sleep(30)"
        val environment = "export MODDIR=${RootShell.quote(module.path)} " +
            "LUOSHU_TASK_SCOPE_PYTHON=python3 LUOSHU_TASKS_DIR=${RootShell.quote(tasks.path)} " +
            "LUOSHU_TMP_DIR=${RootShell.quote(temporary.path)}; "
        try {
            val requestJob = launch {
                executeScopedRequest(
                    "python3 -c ${RootShell.quote(fixture)} ${RootShell.quote(childPidFile.path)}",
                    30_000L, token = "escaped-worker", scopePath = common.resolve("task_scope.sh").path,
                    executor = { command, timeout -> executeProcess(listOf("sh", "-c", environment + command.last()), timeout) },
                )
            }
            job = requestJob
            withTimeout(10_000L) {
                while (!childPidFile.isFile || childPidFile.length() == 0L) delay(10L)
                childProcPid = childPidFile.readText()
                assertTrue(java.io.File("/proc/$childProcPid").exists())
                requestJob.cancelAndJoin()
                while (java.io.File("/proc/$childProcPid").exists()) delay(10L)
            }
            assertFalse(java.io.File("/proc/$childProcPid").exists())
            assertTrue(sentinel.isAlive)
            assertFalse(tasks.resolve("request-escaped-worker.pid").exists())
            assertTrue(temporary.listFiles().orEmpty().isEmpty())
        } finally {
            sentinel.destroyForcibly()
            withContext(NonCancellable) { job?.cancelAndJoin() }
            directory.deleteRecursively()
        }
    }
}
