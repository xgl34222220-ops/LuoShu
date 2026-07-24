package io.github.xgl34222220.luoshu.ui.library

import io.github.xgl34222220.luoshu.FontItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FontLibraryManagementTest {
    @Test
    fun familyBucketsSeparateVariableStaticAndSingleFonts() {
        val sections = groupFontFamilies(
            listOf(
                font("Variable", variable = true, weights = listOf("variable")),
                font("Static", weights = listOf("regular", "bold")),
                font("Single", weights = listOf("regular")),
                font("Broken", valid = false),
            ),
        )

        assertEquals(
            listOf(
                FontFamilyBucket.VARIABLE,
                FontFamilyBucket.STATIC,
                FontFamilyBucket.SINGLE,
                FontFamilyBucket.INVALID,
            ),
            sections.map { it.bucket },
        )
    }

    @Test
    fun copySuffixWithSameResourceSignatureIsMarkedAsDuplicate() {
        val report = analyzeFontLibraryConflicts(
            listOf(
                font("Example Sans", id = "example-sans", size = "12.0 MB"),
                font("Example Sans Copy", id = "example-sans-copy", size = "12.0 MB"),
            ),
        )

        assertEquals(setOf("example-sans", "example-sans-copy"), report.duplicateIds)
        assertTrue(report.nameConflictIds.isEmpty())
    }

    @Test
    fun sameFamilyNameWithDifferentStructureIsMarkedAsConflict() {
        val report = analyzeFontLibraryConflicts(
            listOf(
                font("Example Sans", id = "example-sans", size = "12.0 MB"),
                font(
                    "Example Sans (1)",
                    id = "example-sans-1",
                    size = "25.0 MB",
                    weights = listOf("regular", "bold"),
                ),
            ),
        )

        assertEquals(setOf("example-sans", "example-sans-1"), report.nameConflictIds)
        assertTrue(report.duplicateIds.isEmpty())
    }

    @Test
    fun batchFavoriteAndTagActionsToggleAsAGroup() {
        val ids = setOf("one", "two")
        val favorited = toggleFontFavorite(FontLibraryCollections(), ids)
        assertEquals(ids, favorited.favoriteIds)
        assertTrue(toggleFontFavorite(favorited, ids).favoriteIds.isEmpty())

        val tagged = toggleFontTag(FontLibraryCollections(), ids, "正文")
        assertTrue(ids.all { "正文" in tagged.tags[it].orEmpty() })
        val cleared = toggleFontTag(tagged, ids, "正文")
        assertFalse(cleared.tags.values.any { "正文" in it })
    }

    private fun font(
        name: String,
        id: String = name.lowercase(),
        size: String = "10.0 MB",
        variable: Boolean = false,
        valid: Boolean = true,
        weights: List<String> = listOf("regular"),
    ) = FontItem(
        id = id,
        name = name,
        format = "TTF",
        size = size,
        date = "2026-07-24",
        variable = variable,
        valid = valid,
        error = if (valid) "" else "invalid",
        weights = weights,
        supportsCjk = true,
    )
}
