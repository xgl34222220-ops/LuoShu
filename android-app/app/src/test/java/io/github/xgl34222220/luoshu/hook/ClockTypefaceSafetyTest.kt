package io.github.xgl34222220.luoshu.hook

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ClockTypefaceSafetyTest {
    @Test
    fun privateUseGlyphIsAlwaysPreserved() {
        assertTrue(containsPrivateUseGlyph("\uE8B6"))
        assertTrue(shouldPreserveClockTextTypeface("\uE8B6", null))
    }

    @Test
    fun normalClockTextCanStillUseFinalTypefaceReplacement() {
        assertFalse(containsPrivateUseGlyph("07:00 周一至周五"))
        assertFalse(shouldPreserveClockTextTypeface("07:00 周一至周五", null))
        assertFalse(shouldPreserveClockTextTypeface("计时", "MiSansRCF"))
    }

    @Test
    fun iconEmojiAndMonospaceFamiliesArePreserved() {
        assertTrue(shouldPreserveClockTextTypeface("alarm", "Material Icons"))
        assertTrue(shouldPreserveClockTextTypeface("🙂", "NotoColorEmoji"))
        assertTrue(shouldPreserveClockTextTypeface("00:01", "RobotoMono-Regular"))
    }

    @Test
    fun paintKeepsUnknownCustomFamiliesButAllowsTextFamilies() {
        assertTrue(shouldPreserveClockPaintTypeface(null, systemDefault = false))
        assertTrue(shouldPreserveClockPaintTypeface("clock_icon_font", systemDefault = false))
        assertFalse(shouldPreserveClockPaintTypeface("MiSansRCF", systemDefault = false))
        assertFalse(shouldPreserveClockPaintTypeface("sans-serif", systemDefault = false))
        assertFalse(shouldPreserveClockPaintTypeface(null, systemDefault = true))
    }
}
