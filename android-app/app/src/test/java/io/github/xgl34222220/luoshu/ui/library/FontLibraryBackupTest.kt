package io.github.xgl34222220.luoshu.ui.library

import io.github.xgl34222220.luoshu.FontItem
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FontLibraryBackupTest {
    private val fonts = listOf(
        font("cjk", "CJK Family"),
        font("latin", "Latin Family"),
        font("digit", "Digit Family"),
    )

    @Test
    fun backupRoundTripKeepsAvailableCollectionsAndStudioProfile() {
        val collections = FontLibraryCollections(
            favoriteIds = setOf("cjk", "missing"),
            tags = mapOf("latin" to setOf("英文"), "missing" to setOf("候选")),
        )
        val raw = encodeFontLibraryBackup(collections, validProfileRaw(), fonts)
        val parsed = parseFontLibraryBackup(raw, fonts)

        assertTrue(parsed.valid)
        assertEquals(setOf("cjk"), parsed.collections?.favoriteIds)
        assertEquals(mapOf("latin" to setOf("英文")), parsed.collections?.tags)
        assertTrue(parsed.hasProfile)
        assertNotNull(JSONObject(parsed.profileRaw).optJSONObject("slots"))
        assertTrue(parsed.warnings.any { it.contains("缺少 1 个 Family") })
    }

    @Test
    fun restoreSkipsProfileWhenOneFamilyIsMissing() {
        val parsed = parseFontLibraryBackup(
            encodeFontLibraryBackup(FontLibraryCollections(), validProfileRaw(), fonts),
            fonts.filterNot { it.id == "digit" },
        )

        assertTrue(parsed.valid)
        assertFalse(parsed.hasProfile)
        assertTrue(parsed.warnings.any { it.contains("组合方案未恢复") })
    }

    @Test
    fun migrationReportBlocksIncompleteProfileAndRepairsStaleReferences() {
        val collections = FontLibraryCollections(
            favoriteIds = setOf("cjk", "gone"),
            tags = mapOf("gone" to setOf("正文")),
        )
        val report = buildFontMigrationReport(
            fonts = fonts,
            collections = collections,
            currentProfileRaw = "",
            watchConfigured = true,
            watchPermission = false,
        )

        assertFalse(report.ready)
        assertTrue(report.blockerCount >= 1)
        assertTrue(report.warningCount >= 2)
        assertTrue(report.checks.any { it.id == "collections" && it.repairable })

        val pruned = pruneFontLibraryCollections(collections, fonts.map { it.id }.toSet())
        assertEquals(setOf("cjk"), pruned.favoriteIds)
        assertTrue(pruned.tags.isEmpty())
    }

    @Test
    fun migrationReportAcceptsCompleteProfile() {
        val report = buildFontMigrationReport(
            fonts = fonts,
            collections = FontLibraryCollections(),
            currentProfileRaw = validProfileRaw(),
            watchConfigured = false,
            watchPermission = false,
        )

        assertTrue(report.ready)
        assertEquals(0, report.blockerCount)
    }

    private fun validProfileRaw(): String = """
        {
          "schema": 1,
          "type": "luoshu-studio-profile",
          "name": "test",
          "slots": {
            "cjk": {"fontId":"cjk","fontName":"CJK Family","weight":400,"axes":{"wght":400}},
            "latin": {"fontId":"latin","fontName":"Latin Family","weight":450,"axes":{"wght":450}},
            "digit": {"fontId":"digit","fontName":"Digit Family","weight":500,"axes":{"wght":500}}
          }
        }
    """.trimIndent()

    private fun font(id: String, name: String): FontItem = FontItem(
        id = id,
        name = name,
        format = "TTF",
        size = "1 MB",
        date = "2026-07-24",
        variable = false,
        valid = true,
        error = "",
        weights = listOf("regular"),
        supportsCjk = id == "cjk",
    )
}
