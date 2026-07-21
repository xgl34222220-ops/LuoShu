package io.github.xgl34222220.luoshu.hook

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ClockRuntimeSafetyTest {
    @Test
    fun onlyMainClockProcessReceivesUiHooks() {
        assertTrue(shouldInstallClockUiFontHooks("com.android.deskclock", "com.android.deskclock"))
        assertFalse(shouldInstallClockUiFontHooks("com.android.deskclock", "com.android.deskclock:alarm"))
        assertFalse(shouldInstallClockUiFontHooks("com.android.deskclock", "com.android.deskclock:remote"))
        assertFalse(shouldInstallClockUiFontHooks("com.tencent.mobileqq", "com.tencent.mobileqq"))
    }

    @Test
    fun genericHookDoesNotOverlapQqOrClockRuntimeProcesses() {
        assertTrue(shouldInstallGenericBundledFontHook("com.android.vending", "com.android.vending"))
        assertTrue(shouldInstallGenericBundledFontHook("com.android.deskclock", "com.android.deskclock"))
        assertFalse(
            shouldInstallGenericBundledFontHook(
                "com.android.deskclock",
                "com.android.deskclock:alarm",
            ),
        )
        assertFalse(shouldInstallGenericBundledFontHook("com.tencent.mobileqq", "com.tencent.mobileqq"))
        assertFalse(
            shouldInstallGenericBundledFontHook(
                "io.github.xgl34222220.luoshu.debug",
                "io.github.xgl34222220.luoshu.debug",
            ),
        )
    }

    @Test
    fun alarmPlaybackAndAlertCallersAreCritical() {
        assertTrue(
            isClockAlarmCriticalCall(
                listOf("com.android.deskclock.alarm.AlarmKlaxon", "android.media.MediaPlayer"),
            ),
        )
        assertTrue(
            isClockAlarmCriticalCall(
                listOf("com.miui.clock.ringing.FullScreenAlarmActivity"),
            ),
        )
        assertFalse(
            isClockAlarmCriticalCall(
                listOf("com.android.deskclock.timer.TimerFragment", "android.widget.TextView"),
            ),
        )
    }
}
