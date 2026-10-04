package io.github.xgl34222220.luoshu

import org.junit.Assert.*
import org.junit.Test

class InventoryTimingTest {
    @Test
    fun workerAndOwnedScopeTimingsNeverExportIdentitiesOrArbitraryText() {
        val stderr = """
            [font-request] {"event":"started","token":"private-token","owner":{"pid":4567},"worker":4568,"boot":"private-boot"}
            font /sdcard/LuoShu/fonts/私人字体.ttf failed
            [font-inventory] stage=scan elapsed_ms=12.345 count=1000 code=0
            [font-request] {"event":"finished","token":"private-token","reason":"success","code":0,"cleaned":true,"elapsed_ms":6321.25}
        """.trimIndent()
        assertEquals(listOf(
            "phase=inventory duration_ms=12.345 count=1000 code=0",
            "phase=scope duration_ms=6321.25 code=0 cleaned=true reason=success",
        ), inventoryTimingFields("scan", stderr))
    }

    @Test
    fun deadlineWithoutAWorkerReportRetainsFailureAndCleanupState() {
        assertEquals(listOf("phase=scope duration_ms=8500.0 code=124 cleaned=false reason=timeout"),
            inventoryTimingFields("fingerprint", "[font-request] {\"event\":\"finished\",\"reason\":\"timeout\",\"code\":124,\"cleaned\":false,\"elapsed_ms\":8500}"))
    }

    @Test
    fun malformedUnboundedOrPrivateValuesNeverBecomeLogFields() {
        val invalid = listOf(
            "[font-inventory] stage=scan elapsed_ms=10 count=1 code=0 /private/path",
            "[font-inventory] stage=refresh elapsed_ms=10 count=1 code=0",
            "[font-inventory] stage=scan elapsed_ms=NaN count=1 code=0",
            "[font-inventory] stage=scan elapsed_ms=180001 count=1 code=0",
            "[font-inventory] stage=scan elapsed_ms=10 count=999999999999999999999 code=0",
            "[font-request] {broken}",
            "[font-request] {\"event\":\"finished\",\"reason\":\"private-path\",\"code\":0,\"cleaned\":true,\"elapsed_ms\":1}",
            "[font-request] {\"event\":\"finished\",\"reason\":\"success\",\"code\":\"0\",\"cleaned\":true,\"elapsed_ms\":1}",
            "[font-request] {\"event\":\"finished\",\"reason\":\"success\",\"code\":0,\"cleaned\":\"true\",\"elapsed_ms\":1}",
            "[font-request] {\"event\":\"finished\",\"reason\":\"success\",\"code\":0,\"cleaned\":true,\"elapsed_ms\":\"private-path\"}",
            "[font-request] {\"event\":\"finished\",\"reason\":\"success\",\"code\":0,\"cleaned\":true,\"elapsed_ms\":180001}",
            "[font-request] {\"event\":\"finished\",\"reason\":\"success\",\"code\":0,\"cleaned\":true,\"elapsed_ms\":1,\"token\":\"${"x".repeat(2048)}\"}",
        )
        for (line in invalid) assertTrue(line, inventoryTimingFields("scan", line).isEmpty())
        assertTrue(inventoryTimingFields("scan injected", invalid.joinToString("\n")).isEmpty())
    }
}
