package io.github.xgl34222220.luoshu.hook

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ClockUiDrawSafetyTest {
    @Test
    fun normalClockPagesEnterTheSafeDrawScope() {
        assertTrue(
            shouldEnterClockTextDrawScope(
                packageName = "com.android.deskclock",
                processName = "com.android.deskclock",
                classNames = listOf(
                    "com.android.deskclock.DeskClock",
                    "com.miui.clock.timer.TimerNumberPicker",
                ),
                attached = true,
                shown = true,
            ),
        )
    }

    @Test
    fun alarmAlertAndChildProcessesNeverEnterTheDrawScope() {
        assertFalse(
            shouldEnterClockTextDrawScope(
                packageName = "com.android.deskclock",
                processName = "com.android.deskclock",
                classNames = listOf("com.miui.clock.alarm.AlarmAlertFullScreenActivity"),
                attached = true,
                shown = true,
            ),
        )
        assertFalse(
            shouldEnterClockTextDrawScope(
                packageName = "com.android.deskclock",
                processName = "com.android.deskclock:alarm",
                classNames = listOf("android.view.View"),
                attached = true,
                shown = true,
            ),
        )
        assertFalse(
            shouldEnterClockTextDrawScope(
                packageName = "com.android.deskclock",
                processName = "com.android.deskclock",
                classNames = listOf("com.android.deskclock.DeskClock"),
                attached = false,
                shown = true,
            ),
        )
    }

    @Test
    fun timerDigitsAndLabelsReplaceButIconsStayOriginal() {
        assertTrue(shouldReplaceClockDrawText("00:05:00", "Mitype2019"))
        assertTrue(shouldReplaceClockDrawText(":", "MitypeMono"))
        assertTrue(shouldReplaceClockDrawText("计时", "sans-serif"))
        assertFalse(shouldReplaceClockDrawText(":", null))
        assertFalse(shouldReplaceClockDrawText("\uE8B6", null))
        assertFalse(shouldReplaceClockDrawText("图标", "MaterialIcons"))
        assertFalse(shouldReplaceClockDrawText("🙂", "NotoColorEmoji"))
    }

    @Test
    fun replacementWidthIsFittedWithoutStretchingNarrowerFonts() {
        assertEquals(1f, fittedClockTextScaleX(1f, 100f, 80f), 0.001f)
        assertEquals(0.8f, fittedClockTextScaleX(1f, 80f, 100f), 0.001f)
        assertEquals(0.72f, fittedClockTextScaleX(0.9f, 80f, 100f), 0.001f)
    }

    @Test
    fun pathologicalWideDisplayFontsUseConservativeMinimumScale() {
        assertEquals(0.68f, fittedClockTextScaleX(1f, 50f, 100f), 0.001f)
        assertEquals(0.85f, fittedClockTextScaleX(0.85f, 0f, 100f), 0.001f)
    }

    @Test
    fun legacyBroadClockCallbacksAreAlwaysCritical() {
        assertTrue(
            isClockAlarmCriticalCall(
                listOf(
                    "io.github.xgl34222220.luoshu.hook.AppBundledFontHook",
                    "android.graphics.Typeface",
                ),
            ),
        )
    }
}
