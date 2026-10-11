package io.github.xgl34222220.luoshu.ui.logs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class XmlParityConclusionTest {
    @Test
    fun okParityWithoutShadowIsOneQuietLine() {
        assertEquals(
            "三路字体配置一致（FontManager / fonts.xml / font_fallback.xml）",
            xmlParityConclusion("ok", "none"),
        )
    }

    @Test
    fun mismatchAndShadowAreBothNamed() {
        val line = xmlParityConclusion("mismatch:sans-serif(fm=A.ttf,fontsXml=B.ttf)", "NotoColorEmoji")
        assertTrue(line.startsWith("三路字体配置不一致"))
        assertTrue(line.endsWith("被系统热更新字体遮盖：NotoColorEmoji"))
    }

    @Test
    fun missingResultStaysHidden() {
        assertEquals("", xmlParityConclusion("", ""))
        assertEquals("三路字体配置一致性未能采集", xmlParityConclusion("not-collected", "not-collected"))
    }
}
