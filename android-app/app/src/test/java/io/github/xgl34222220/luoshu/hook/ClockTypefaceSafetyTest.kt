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
    fun anonymousLargeTimerPaintIsReplacedButSmallUnknownIconPaintIsPreserved() {
        assertFalse(
            shouldPreserveClockPaintTypeface(
                familyName = null,
                systemDefault = false,
                textSizeSp = 56f,
                callerClassNames = emptyList(),
            ),
        )
        assertTrue(
            shouldPreserveClockPaintTypeface(
                familyName = null,
                systemDefault = false,
                textSizeSp = 22f,
                callerClassNames = emptyList(),
            ),
        )
    }

    @Test
    fun callerHintsOverrideAmbiguousAnonymousPaints() {
        assertFalse(
            shouldPreserveClockPaintTypeface(
                familyName = null,
                systemDefault = false,
                textSizeSp = 18f,
                callerClassNames = listOf("miuix.pickerwidget.widget.NumberPicker"),
            ),
        )
        assertTrue(
            shouldPreserveClockPaintTypeface(
                familyName = null,
                systemDefault = false,
                textSizeSp = 48f,
                callerClassNames = listOf("com.google.android.material.navigation.NavigationBarItemView"),
            ),
        )
    }

    @Test
    fun namedFamiliesStillUseExplicitRules() {
        assertTrue(
            shouldPreserveClockPaintTypeface(
                familyName = "clock_icon_font",
                systemDefault = false,
                textSizeSp = 64f,
                callerClassNames = emptyList(),
            ),
        )
        assertFalse(
            shouldPreserveClockPaintTypeface(
                familyName = "MiSansRCF",
                systemDefault = false,
                textSizeSp = 20f,
                callerClassNames = emptyList(),
            ),
        )
        assertFalse(
            shouldPreserveClockPaintTypeface(
                familyName = "sans-serif",
                systemDefault = false,
                textSizeSp = 20f,
                callerClassNames = emptyList(),
            ),
        )
        assertFalse(
            shouldPreserveClockPaintTypeface(
                familyName = null,
                systemDefault = true,
                textSizeSp = 20f,
                callerClassNames = emptyList(),
            ),
        )
    }
}
