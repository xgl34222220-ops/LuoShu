package io.github.xgl34222220.luoshu

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class GoogleFontDiagnosticEvidenceTest {
    private fun evidence(user: Int = 0, phase: String = "before-maintenance", time: Long = 1000L, boot: String = "aaaaaaaaaaaaaaaaaaaa") =
        """{"schema":"luoshu-google-font-diagnostic-v1","user":$user,"phase":"$phase","capturedAtEpochMs":$time,"bootToken":"$boot","collection":{"complete":false},"component":{"classification":"unknown"}}"""

    @Test fun collectorCommandIsReadOnlyPinnedAndBoundToTheAppUser() {
        val command = googleFontDiagnosticCommand(10, "explicit-report")
        assertTrue(command.contains("google_font_diagnostic.sh"))
        assertTrue(command.contains("--user 10 --phase explicit-report"))
        listOf("reconcile-owned", "refresh", "apply", "pm disable", "kill", "--user all").forEach {
            assertFalse(command.contains(it))
        }
    }
    @Test(expected = IllegalArgumentException::class) fun arbitraryPhaseIsRejected() {
        googleFontDiagnosticCommand(0, "explicit-report;reboot")
    }
    @Test(expected = IllegalArgumentException::class) fun anotherUserReportIsRejected() {
        parseGoogleFontDiagnostic(evidence(10), 0, "before-maintenance")
    }
    @Test(expected = IllegalArgumentException::class) fun fractionalUserIsNotRoundedIntoTheAppUser() {
        parseGoogleFontDiagnostic(evidence().replace("\"user\":0", "\"user\":0.2"), 0, "before-maintenance")
    }
    @Test(expected = IllegalArgumentException::class) fun explicitReportCannotMasqueradeAsPreflight() {
        parseGoogleFontDiagnostic(evidence(phase = "explicit-report"), 0, "before-maintenance")
    }
    @Test(expected = IllegalArgumentException::class) fun missingSchemaIsRejected() {
        parseGoogleFontDiagnostic(evidence().replace(GOOGLE_FONT_DIAGNOSTIC_SCHEMA, "unknown"), 0, "before-maintenance")
    }
    @Test(expected = IllegalArgumentException::class) fun oversizedReportIsRejectedBeforeParsing() {
        parseGoogleFontDiagnostic(" ".repeat(131073), 0, "before-maintenance")
    }
    @Test fun incompleteCollectionIsPreservedAsUnknownRatherThanFontAcceptance() {
        val report = parseGoogleFontDiagnostic(evidence(), 0, "before-maintenance")
        assertFalse(report.getJSONObject("collection").getBoolean("complete"))
        assertEquals("unknown", report.getJSONObject("component").getString("classification"))
    }
    @Test fun previousEvidenceKeepsItsPhaseAgeAndBootIdentity() {
        val current = JSONObject(evidence(phase = "explicit-report", time = 9000L))
        val previous = JSONObject(evidence())
        val result = attachPreviousGoogleFontEvidence(current, previous)
        assertEquals(8000L, result.getLong("previousSnapshotAgeMs"))
        assertTrue(result.getBoolean("previousSnapshotSameBoot"))
        assertEquals("before-maintenance", result.getJSONObject("previousSnapshot").getString("phase"))
        assertFalse(current.has("previousSnapshot"))
    }
    @Test fun anotherBootAndClockRegressionAreNotPresentedAsFreshEvidence() {
        val result = attachPreviousGoogleFontEvidence(JSONObject(evidence(phase = "explicit-report", time = 500L, boot = "b")),
            JSONObject(evidence()))
        assertFalse(result.getBoolean("previousSnapshotSameBoot"))
        assertTrue(result.isNull("previousSnapshotAgeMs"))
    }
    @Test fun firstExportDoesNotInventAMaintenanceSnapshot() {
        assertFalse(attachPreviousGoogleFontEvidence(JSONObject(evidence(phase = "explicit-report")), null)
            .getBoolean("previousSnapshotAvailable"))
    }
    @Test fun missingBootIdentityCannotBecomeASameBootClaim() {
        val current = JSONObject(evidence(phase = "explicit-report")).put("bootToken", JSONObject.NULL)
        val previous = JSONObject(evidence()).put("bootToken", JSONObject.NULL)
        assertFalse(attachPreviousGoogleFontEvidence(current, previous).getBoolean("previousSnapshotSameBoot"))
    }
}
