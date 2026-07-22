package io.github.xgl34222220.luoshu.ui.font

import io.github.xgl34222220.luoshu.FontItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
    fun compactCardPreviewNeverWraps() {
        val font = font(weights = listOf("regular"))

        assertEquals("洛书 Aa 0123456789", fontPreviewText(font))
        assertFalse(fontPreviewText(font).contains('\n'))
        assertTrue(fontPreviewText(font, detailed = true).contains('\n'))
    }

    @Test
    fun latinOnlyFontExplainsWhyChineseLooksLikeSystemDefault() {
        val font = font(weights = listOf("regular"), supportsCjk = false)

        assertTrue(fontCapabilityLabel(font).startsWith("仅拉丁"))
        assertEquals("Aa Hello 0123456789", fontPreviewText(font))
        assertTrue(fontPreviewText(font, detailed = true).contains("中文回退系统字体"))
    }

    @Test
    fun regularRemainsThePreferredStaticPreview() {
        val font = font(weights = listOf("thin", "regular", "black"))

        assertEquals(400, fontPreviewWeight(font))
    }

    private fun font(weights: List<String>, supportsCjk: Boolean = true) = FontItem(
        id = "SuperHualunwan",
        name = "超级花轮丸",
        format = "TTF",
        size = "23.0 MB",
        date = "2026-07-22",
        variable = false,
        valid = true,
        error = "",
        weights = weights,
        supportsCjk = supportsCjk,
    )
}
