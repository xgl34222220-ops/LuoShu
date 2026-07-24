package io.github.xgl34222220.luoshu.ui.studio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StudioGlyphBrowserTest {
    @Test
    fun codePointsKeepSurrogatePairsTogether() {
        val points = glyphCodePoints("A😀中")

        assertEquals(3, points.size)
        assertEquals(0x1F600, points[1])
    }

    @Test
    fun pagingUsesUnicodeCodePoints() {
        val source = "A😀中B"

        assertEquals("A😀", glyphPage(source, page = 0, pageSize = 2))
        assertEquals("中B", glyphPage(source, page = 1, pageSize = 2))
        assertEquals("", glyphPage(source, page = 2, pageSize = 2))
    }

    @Test
    fun categoriesHaveStableUniqueIds() {
        assertTrue(glyphBrowserCategories.isNotEmpty())
        assertEquals(glyphBrowserCategories.size, glyphBrowserCategories.map { it.id }.toSet().size)
    }
}
