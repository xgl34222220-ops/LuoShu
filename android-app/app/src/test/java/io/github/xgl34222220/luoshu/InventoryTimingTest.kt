package io.github.xgl34222220.luoshu

import org.junit.Assert.*
import org.junit.Test

class InventoryTimingTest {
    private val detail = "[font-inventory-detail] stage=scan storage_ms=1.0 snapshot_ms=2.0 cache_ms=3.0 build_ms=0.0 verify_ms=4.0 write_ms=0.0 output_ms=5.0 cache_hit=1 snapshot_count=2 build_count=0 write_count=0 code=0"

    @Test
    fun subphasesExportOnlyFixedSpansAndCountsTogetherWithExistingTotals() {
        val fields = inventoryTimingFields("scan", "$detail\n[font-inventory] stage=scan elapsed_ms=16 count=1000 code=0\n" +
            "[font-request] {\"event\":\"finished\",\"reason\":\"success\",\"code\":0,\"cleaned\":true,\"elapsed_ms\":6321.25,\"token\":\"private-token\"}")
        assertEquals(3, fields.size)
        assertEquals(detail.removePrefix("[font-inventory-detail] stage=scan ").let { "phase=inventory_detail $it" }, fields[0])
        assertEquals("phase=inventory duration_ms=16.0 count=1000 code=0", fields[1])
        assertEquals("phase=scope duration_ms=6321.25 code=0 cleaned=true reason=success", fields[2])
        assertFalse(fields.any { "private" in it })
    }

    @Test
    fun subphaseMalformedOrUnboundedValuesCannotReachLocalAppLogs() {
        for (line in listOf(detail + " /private/path", detail.replace("stage=scan", "stage=refresh"),
            detail.replace("snapshot_ms=2.0", "snapshot_ms=NaN"),
            detail.replace("snapshot_ms=2.0", "snapshot_ms=180001.0"),
            detail.replace("snapshot_count=2", "snapshot_count=3"),
            detail.replace("write_count=0", "write_count=999999999999999999999"),
            detail.replace("build_count=0", "build_count=true"),
            detail.replace("cache_hit=1", "cache_hit=2"), detail.replace("code=0", "code=256"))) {
            assertTrue(line, inventoryTimingFields("scan", line).isEmpty())
        }
    }

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
