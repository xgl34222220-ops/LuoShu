package io.github.xgl34222220.luoshu.hook

private val CLOCK_CRITICAL_UI_MARKERS = listOf(
    "alarmalert",
    "alarmring",
    "ringactivity",
    "ringing",
    "ringtone",
    "klaxon",
    "prealarm",
    "fullscreenalarm",
    "fullscreennotification",
    "alertactivity",
    "alertservice",
    "notificationservice",
    "snooze",
    "dismissalarm",
)

internal fun isClockCriticalUiClass(classNames: List<String>): Boolean {
    val names = classNames.joinToString("|").lowercase()
    return CLOCK_CRITICAL_UI_MARKERS.any(names::contains)
}

internal fun shouldEnterClockTextDrawScope(
    packageName: String,
    processName: String,
    classNames: List<String>,
    attached: Boolean,
    shown: Boolean,
): Boolean {
    if (!shouldInstallClockUiFontHooks(packageName, processName)) return false
    if (!attached || !shown) return false
    return !isClockCriticalUiClass(classNames)
}

internal fun shouldReplaceClockDrawText(
    text: CharSequence?,
    familyName: String?,
): Boolean {
    if (text.isNullOrEmpty() || containsPrivateUseGlyph(text)) return false
    val family = familyName?.trim()?.lowercase().orEmpty()
    if (family.isNotEmpty() && CLOCK_PROTECTED_FONT_MARKERS.any(family::contains)) return false
    return text.any { character ->
        character.isLetterOrDigit() || Character.UnicodeScript.of(character.code) in setOf(
            Character.UnicodeScript.HAN,
            Character.UnicodeScript.HIRAGANA,
            Character.UnicodeScript.KATAKANA,
            Character.UnicodeScript.HANGUL,
        )
    }
}
