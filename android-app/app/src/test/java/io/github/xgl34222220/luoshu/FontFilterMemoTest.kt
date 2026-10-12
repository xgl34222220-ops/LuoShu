package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class FontFilterMemoTest {
    private fun font(id: String, name: String = id, format: String = "TTF") = FontItem(
        id = id, name = name, format = format, size = "1 MB", date = "", variable = false,
        valid = true, error = "", weights = emptyList(),
    )

    private val library = listOf(font("misans", "MiSans VF"), font("noto", "Noto Sans SC", "OTF"), font("lxgw", "霞鹜文楷"))

    @Test
    fun filtersByNameIdAndFormatIgnoringCaseAndSurroundingSpaces() {
        assertSame(library, filterFonts(library, "   "))
        assertEquals(listOf("misans"), filterFonts(library, " misans vf ").map { it.id })
        assertEquals(listOf("noto"), filterFonts(library, "otf").map { it.id })
        assertEquals(listOf("lxgw"), filterFonts(library, "文楷").map { it.id })
    }

    @Test
    fun repeatedReadsWithTheSameListAndQueryDoNotRefilter() {
        var calls = 0
        val memo = FontFilterMemo { fonts, query -> calls += 1; filterFonts(fonts, query) }
        val first = memo.filter(library, "sans")
        repeat(50) { assertSame(first, memo.filter(library, "sans")) }
        assertEquals(1, calls)
    }

    @Test
    fun aNewQueryOrANewFontListRecomputes() {
        var calls = 0
        val memo = FontFilterMemo { fonts, query -> calls += 1; filterFonts(fonts, query) }
        assertEquals(2, memo.filter(library, "sans").size)
        assertEquals(1, memo.filter(library, "noto").size)
        val updated = library + font("roboto", "Roboto Sans")
        assertEquals(1, memo.filter(updated, "noto").size)
        assertEquals(listOf("roboto"), memo.filter(updated, "roboto").map { it.id })
        assertEquals(4, calls)
    }
}
