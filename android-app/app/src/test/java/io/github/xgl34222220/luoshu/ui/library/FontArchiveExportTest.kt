package io.github.xgl34222220.luoshu.ui.library

import io.github.xgl34222220.luoshu.FontItem
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FontArchiveExportTest {
    @Test
    fun archiveSegmentRemovesUnsafePathCharacters() {
        val value = safeFontArchiveSegment("  Demo/Family:Bold\\Name\n  ")

        assertEquals("Demo-Family-Bold-Name", value)
        assertFalse(value.contains('/'))
        assertFalse(value.contains('\\'))
    }

    @Test
    fun archiveSelectionRequiresExistingValidFamilies() {
        val fonts = listOf(font("a", true), font("b", false))

        assertEquals(listOf("a"), selectFontArchiveFamilies(fonts, setOf("a")).map { it.id })
        assertTrue(runCatching { selectFontArchiveFamilies(fonts, setOf("missing")) }.isFailure)
        assertTrue(runCatching { selectFontArchiveFamilies(fonts, setOf("b")) }.isFailure)
    }

    @Test
    fun manifestContainsFilesAndChecksumsWithoutPrivatePaths() {
        val raw = buildFontArchiveManifest(
            records = listOf(
                FontArchiveFileRecord(
                    familyId = "family-a",
                    familyName = "Family A",
                    archivePath = "fonts/Family-A/font-001.ttf",
                    bytes = 1234,
                    sha256 = "a".repeat(64),
                ),
                FontArchiveFileRecord(
                    familyId = "family-a",
                    familyName = "Family A",
                    archivePath = "fonts/Family-A/font-002.otf",
                    bytes = 5678,
                    sha256 = "b".repeat(64),
                ),
            ),
            appVersion = "2.2.2-alpha1",
            createdAt = "2026-07-24T22:00:00",
        )
        val root = JSONObject(raw)

        assertEquals("luoshu-font-archive", root.getString("type"))
        assertTrue(root.getBoolean("includesFontFiles"))
        assertEquals(1, root.getInt("familyCount"))
        assertEquals(2, root.getInt("fileCount"))
        assertEquals(6912L, root.getLong("totalBytes"))
        assertFalse(raw.contains("/data/"))
        assertFalse(raw.contains("/sdcard/"))
    }

    private fun font(id: String, valid: Boolean): FontItem = FontItem(
        id = id,
        name = "Family $id",
        format = "TTF",
        size = "1 MB",
        date = "2026-07-24",
        variable = false,
        valid = valid,
        error = if (valid) "" else "invalid",
        weights = listOf("regular"),
        supportsCjk = true,
    )
}
