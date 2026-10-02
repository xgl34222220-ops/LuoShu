package io.github.xgl34222220.luoshu

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class FontApplyAdmissionTest {
    private val fingerprint = "font-selection-v1:" + "a".repeat(64)
    private fun preflight(data: String = "\"valid\":true,\"fingerprint\":\"$fingerprint\"") =
        ShellResult(0, "{\"status\":\"ok\",\"data\":{$data}}", "")
    private val accepted = ShellResult(0, "{\"status\":\"ok\",\"data\":{\"task\":\"task-1\"}}", "")

    @Test fun explicitPreflightIdentityIsPassedToBoundedAdmission() = runBlocking {
        val events = mutableListOf<Pair<String, Int>>()
        var command = ""
        val task = admitFontApply("/module/bridge.sh", "A'Font", { id ->
            assertEquals("A'Font", id); preflight()
        }, { request, timeout ->
            command = request; assertEquals(20_000L, timeout); accepted
        }, { stage, duration, code -> assertTrue(duration >= 0); events += stage to code })
        assertEquals("task-1", task)
        assertEquals("sh '/module/bridge.sh' switch_start 'A'\\''Font' '$fingerprint'", command)
        assertEquals(listOf("preflight" to 0, "admission" to 0), events)
    }

    @Test fun defaultRestorationSkipsFontPreflight() = runBlocking {
        val task = admitFontApply("bridge", "default", { error("must not preflight default") },
            { command, _ -> assertTrue(command.endsWith("'default' ''")); accepted })
        assertEquals("task-1", task)
    }

    @Test fun preflightTimeoutNeverStartsTaskAndReportsCode() = runBlocking {
        val events = mutableListOf<Pair<String, Int>>()
        try {
            admitFontApply("bridge", "Demo", { ShellResult(124, "", "命令执行超时") },
                { _, _ -> error("must not admit failed preflight") }, { stage, _, code -> events += stage to code })
            fail("must reject timeout")
        } catch (error: IllegalStateException) { assertEquals("命令执行超时", error.message) }
        assertEquals(listOf("preflight" to 124), events)
    }

    @Test fun structuredPreflightRejectionWinsOverSupervisorDiagnostics() = runBlocking {
        try {
            admitFontApply("bridge", "Demo", {
                ShellResult(1, "{\"status\":\"error\",\"message\":\"字体文件已变化，请刷新后重试\"}",
                    "[font-request] ownership diagnostics")
            }, { _, _ -> error("unexpected admission") })
            fail("must reject changed font")
        } catch (error: IllegalStateException) {
            assertEquals("字体文件已变化，请刷新后重试", error.message)
        }
    }

    @Test fun missingOrInvalidFingerprintAndValidityCannotAdmit() = runBlocking {
        for (data in listOf("\"valid\":true", "\"valid\":false,\"fingerprint\":\"$fingerprint\"",
                            "\"valid\":true,\"fingerprint\":\"other\"", "\"fingerprint\":\"$fingerprint\"")) {
            try {
                admitFontApply("bridge", "Demo", { preflight(data) }, { _, _ -> error("unexpected admission") })
                fail("must reject malformed preflight")
            } catch (error: IllegalStateException) { assertNotEquals("unexpected admission", error.message) }
        }
    }

    @Test fun cancellationIsNotConvertedToAcceptanceAndRecordsStage() = runBlocking {
        val events = mutableListOf<Pair<String, Int>>()
        try {
            admitFontApply("bridge", "Demo", { throw CancellationException("cancel") },
                { _, _ -> error("must not admit cancellation") }, { stage, _, code -> events += stage to code })
            fail("must cancel")
        } catch (_: CancellationException) { }
        assertEquals(listOf("preflight" to 130), events)
    }

    @Test fun admissionFailureIsDistinguishedFromPreflight() = runBlocking {
        val events = mutableListOf<Pair<String, Int>>()
        try {
            admitFontApply("bridge", "Demo", { preflight() }, { _, _ -> ShellResult(124, "", "admission timeout") },
                { stage, _, code -> events += stage to code })
            fail("must reject admission")
        } catch (error: IllegalStateException) { assertEquals("admission timeout", error.message) }
        assertEquals(listOf("preflight" to 0, "admission" to 124), events)
    }

    @Test fun missingTaskCannotLookAccepted() = runBlocking {
        try {
            admitFontApply("bridge", "Demo", { preflight() }, { _, _ -> ShellResult(0, "{\"status\":\"ok\"}", "") })
            fail("missing task must fail")
        } catch (error: IllegalStateException) { assertEquals("字体任务 ID 缺失", error.message) }
    }
}
