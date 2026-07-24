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
        assertEquals("多字重 · 2 档", fontCapabilityLabel(font))
        assertFalse(fontCapabilityLabel(font).contains("常规 400"))
    }

    @Test
    fun allCardsUseTheSameStablePreviewCopy() {
        val cjk = font(weights = listOf("regular"), supportsCjk = true)
        val latin = font(weights = listOf("regular"), supportsCjk = false)
        val compact = "洛书字体 Aa 123"
        val detailed = "洛书字体 Aa\n中文 ABC 123"

        assertEquals(compact, fontPreviewText(cjk))
        assertEquals(compact, fontPreviewText(latin))
        assertEquals(detailed, fontPreviewText(cjk, detailed = true))
        assertEquals(detailed, fontPreviewText(latin, detailed = true))
    }

    @Test
    fun compactCardPreviewNeverWraps() {
        val font = font(weights = listOf("regular"))

        assertFalse(fontPreviewText(font).contains('\n'))
        assertEquals(2, fontPreviewText(font, detailed = true).lines().size)
    }

    @Test
    fun latinOnlyDifferenceIsExpressedByCapabilityLabel() {
        val font = font(weights = listOf("regular"), supportsCjk = false)

        assertTrue(fontCapabilityLabel(font).startsWith("拉丁"))
        assertEquals("洛书字体 Aa\n中文 ABC 123", fontPreviewText(font, detailed = true))
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
