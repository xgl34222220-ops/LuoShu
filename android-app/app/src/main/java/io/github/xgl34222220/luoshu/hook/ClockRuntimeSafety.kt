package io.github.xgl34222220.luoshu.hook

internal val CLOCK_PACKAGES = setOf("com.android.deskclock", "com.miui.clock")

private val CLOCK_ALARM_CRITICAL_CALL_MARKERS = listOf(
    // The legacy broad Clock hook remains in the generic entry for Play/other apps, but every Clock
    // callback contains AppBundledFontHook in its stack. Treat it as critical so all old Clock
    // factory/resource/Paint replacement paths become inert; ClockUiDrawFontHook is the only active
    // Clock replacement policy.
    "appbundledfonthook",
    "alarmalert",
    "alarmactivity",
    "alarmreceiver",
    "alarmservice",
    "alarmstate",
    "alarmklaxon",
    "alarmprealarm",
    "alarmnotification",
    "ringactivity",
    "ringing",
    "ringtone",
    "klaxon",
    "fullscreenalarm",
    "fullscreennotification",
    "alertactivity",
    "alertservice",
    "notificationservice",
    "mediaplayer",
    "audiotrack",
    "audiofocus",
)

/**
 * Clock UI hooks are intentionally limited to the package's main process.
 *
 * OEM clock apps commonly move alarm receivers, ringtone playback and full-screen alerts into
 * package-suffixed processes. Font replacement has no value there and must never be able to affect
 * alarm lifetime, audio focus or notification delivery.
 */
internal fun shouldInstallClockUiFontHooks(packageName: String, processName: String): Boolean =
    packageName in CLOCK_PACKAGES && processName == packageName

/**
 * Generic bundled-font replacement must not overlap the dedicated QQ policy or functional clock
 * processes. Keeping this as a pure function gives CI a direct regression gate for scope isolation.
 */
internal fun shouldInstallGenericBundledFontHook(packageName: String, processName: String): Boolean {
    if (packageName.startsWith("io.github.xgl34222220.luoshu")) return false
    if (packageName in QQ_PACKAGES) return false
    if (packageName in CLOCK_PACKAGES) return shouldInstallClockUiFontHooks(packageName, processName)
    return true
}

/** Returns true for legacy Clock hooks or call stacks belonging to alarm playback/alert execution. */
internal fun isClockAlarmCriticalCall(callerClassNames: List<String>): Boolean {
    val callers = callerClassNames.joinToString("|").lowercase()
    return CLOCK_ALARM_CRITICAL_CALL_MARKERS.any(callers::contains)
}
