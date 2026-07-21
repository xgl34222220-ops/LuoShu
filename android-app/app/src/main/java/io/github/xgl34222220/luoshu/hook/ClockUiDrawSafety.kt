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

private val CLOCK_TEXT_SCRIPTS = setOf(
    Character.UnicodeScript.HAN,
    Character.UnicodeScript.HIRAGANA,
    Character.UnicodeScript.KATAKANA,
    Character.UnicodeScript.HANGUL,
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

    // Time separators may be drawn in their own call. Known Clock text families are safe even when
    // the current fragment contains only ':' or '.'. Unknown punctuation-only Paints stay original.
    if (family.isNotEmpty() && CLOCK_TEXT_FONT_MARKERS.any(family::contains)) return true

    return text.any { character ->
        character.isLetterOrDigit() || Character.UnicodeScript.of(character.code) in CLOCK_TEXT_SCRIPTS
    }
}
