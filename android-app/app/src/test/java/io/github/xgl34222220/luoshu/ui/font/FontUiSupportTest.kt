package io.github.xgl34222220.luoshu.ui.font

import io.github.xgl34222220.luoshu.FontItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class FontUiSupportTest {
    @Test
    fun incompleteThinBlackFamilyUsesBlackForCardPreview() {
        val font = font(weights = listOf("thin", "black"))

        assertEquals(900, fontPreviewWeight(font))
        assertEquals("多字重 · 100 / 900", fontCapabilityLabel(font))
        assertFalse(fontCapabilityLabel(font).contains("常规 400"))
    }

    @Test
    fun regularRemainsThePreferredStaticPreview() {
        val font = font(weights = listOf("thin", "regular", "black"))

        assertEquals(400, fontPreviewWeight(font))
    }

    private fun font(weights: List<String>) = FontItem(
        id = "SuperHualunwan",
        name = "超级花轮丸",
        format = "TTF",
        size = "23.0 MB",
        date = "2026-07-22",
        variable = false,
        valid = true,
        error = "",
        weights = weights,
    )
}
