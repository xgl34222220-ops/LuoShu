package io.github.xgl34222220.luoshu.ui.home

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceTestMatrixTest {
    private val passedChecks = listOf(
        DeviceAcceptanceCheck("auto", "自动", "通过", true, true),
        DeviceAcceptanceCheck("manual", "人工", "通过", true, false),
    )

    private val trust = DeviceTrustState(
        loading = false,
        inventory = "available",
        alignment = "verified",
        mode = "aligned",
        cachePending = false,
    )

    @Test
    fun passingRecordIsAnonymousAndCapsNote() {
        val state = readyState(currentFont = "我的私人字体名称")
        val record = buildDeviceTestMatrixRecord(
            state = state,
            trust = trust,
            checks = passedChecks,
            note = "x".repeat(400),
            recordedAt = 1000L,
            androidApi = 36,
        )

        assertEquals(DeviceTestResult.PASS, record.result)
        assertEquals("custom", record.profileKind)
        assertEquals(200, record.note.length)
        assertFalse(record.toString().contains(state.currentFont))
    }

    @Test
    fun sameVersionAndEnvironmentReplacesOlderRecord() {
        val first = buildDeviceTestMatrixRecord(readyState(), trust, passedChecks, "old", 1000L, 36)
        val second = buildDeviceTestMatrixRecord(readyState(), trust, passedChecks, "new", 2000L, 36)

        val merged = mergeDeviceTestMatrixRecord(listOf(first), second)

        assertEquals(1, merged.size)
        assertEquals("new", merged.single().note)
        assertEquals(2000L, merged.single().recordedAt)
    }

    @Test
    fun prereleaseReportBlocksOldVersionAndAcceptsTargetCandidate() {
        val oldState = readyState(version = "v2.2.1")
        val oldReport = buildPreReleaseReadinessReport(
            state = oldState,
            trust = trust,
            checks = passedChecks,
            records = emptyList(),
            now = 2000L,
        )
        assertFalse(oldReport.ready)
        assertTrue(oldReport.checks.any { it.id == "version" && it.severity == PreReleaseGateSeverity.BLOCKER })

        val candidateState = readyState(version = "v2.2.2-alpha1")
        val record = buildDeviceTestMatrixRecord(candidateState, trust, passedChecks, "", 1000L, 36)
        val readyReport = buildPreReleaseReadinessReport(
            state = candidateState,
            trust = trust,
            checks = passedChecks,
            records = listOf(record),
            now = 2000L,
        )

        assertTrue(readyReport.ready)
        assertEquals(0, readyReport.blockerCount)
        assertTrue(readyReport.warningCount >= 1)
    }

    @Test
    fun exportedMatrixOmitsDeviceAndFontIdentity() {
        val state = readyState(currentFont = "SecretFamily")
        val record = buildDeviceTestMatrixRecord(state, trust, passedChecks, "正常", 1000L, 36)
        val report = buildPreReleaseReadinessReport(state, trust, passedChecks, listOf(record), now = 2000L)
        val raw = encodeDeviceTestMatrix(listOf(record), report, generatedAt = 3000L)
        val root = JSONObject(raw)

        assertEquals("luoshu-device-test-matrix", root.getString("type"))
        assertFalse(raw.contains("SecretFamily"))
        assertFalse(raw.contains("model", ignoreCase = true))
        assertFalse(raw.contains("fingerprint", ignoreCase = true))
        assertFalse(raw.contains("serial", ignoreCase = true))
        assertFalse(raw.contains("/data/"))
    }

    private fun readyState(
        version: String = "v2.2.2-alpha1",
        currentFont: String = "自定义字体",
    ): HomeUiState = HomeUiState(
        version = version,
        currentFont = currentFont,
        rootGranted = true,
        rootManager = "KernelSU",
        moduleInstalled = true,
        mountEngine = "Magic Mount",
        taskRunning = false,
        rebootRequired = false,
    )
}
