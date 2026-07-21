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

private const val CLOCK_MIN_HORIZONTAL_SCALE = 0.68f

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

/**
 * TextView-only selection is intentionally narrower than the Canvas path.
 *
 * HyperOS renders alarm rows, world-clock values and the stopwatch counter through TextView/Layout
 * paths that may bypass the hooked Canvas base methods. Only time-bearing TextViews are replaced so
 * page titles and normal labels keep the already-correct global system font. Known clock-family
 * separator-only views are included because some layouts place ':' in their own TextView.
 */
internal fun shouldReplaceClockTextViewText(
    text: CharSequence?,
    familyName: String?,
): Boolean {
    if (text.isNullOrEmpty() || containsPrivateUseGlyph(text)) return false
    val family = familyName?.trim()?.lowercase().orEmpty()
    if (family.isNotEmpty() && CLOCK_PROTECTED_FONT_MARKERS.any(family::contains)) return false
    if (text.any(Char::isDigit)) return true
    val separatorOnly = text.all { character ->
        character.isWhitespace() || character == ':' || character == '.' || character == '·'
    }
    return separatorOnly && family.isNotEmpty() && CLOCK_TEXT_FONT_MARKERS.any(family::contains)
}

/**
 * Keeps a replacement face inside the width the Clock originally measured with its stock face.
 *
 * HyperOS NumberPicker/world-clock views calculate item bounds before drawing. Replacing only the
 * Typeface at draw time can make the new glyph run wider than that precomputed bound, clipping the
 * final digit. We never stretch a narrower replacement; wider faces are compressed only as much as
 * required, with a conservative lower bound for pathological display fonts.
 */
internal fun fittedClockTextScaleX(
    originalScaleX: Float,
    originalWidthPx: Float,
    replacementWidthPx: Float,
): Float {
    if (!originalScaleX.isFinite() || originalScaleX <= 0f) return 1f
    if (
        !originalWidthPx.isFinite() ||
        !replacementWidthPx.isFinite() ||
        originalWidthPx <= 0f ||
        replacementWidthPx <= 0f ||
        replacementWidthPx <= originalWidthPx
    ) {
        return originalScaleX
    }
    val ratio = (originalWidthPx / replacementWidthPx).coerceIn(CLOCK_MIN_HORIZONTAL_SCALE, 1f)
    return originalScaleX * ratio
}
