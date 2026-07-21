package io.github.xgl34222220.luoshu.hook

internal val CLOCK_TEXT_FONT_MARKERS = listOf(
    "productsans",
    "product_sans",
    "googlesans",
    "google_sans",
    "misansrcf",
    "misans",
    "mitype2019",
    "mitypemono",
    "roboto",
    "sourcesans",
    "source_sans",
)

internal val CLOCK_PROTECTED_FONT_MARKERS = listOf(
    "emoji",
    "symbol",
    "glyph",
    "misymbol",
    "icon",
    "materialicons",
    "material_symbols",
    "dingbat",
    "barcode",
    "qrcode",
    "monospace",
    "roboto-mono",
    "robotomono",
)

private val CLOCK_GENERIC_TEXT_FAMILIES = setOf(
    "sans",
    "sans-serif",
    "sans-serif-medium",
    "sans-serif-condensed",
    "serif",
    "cursive",
    "casual",
)

private val CLOCK_TEXT_DRAW_CALLERS = listOf(
    "numberpicker",
    "timepicker",
    "datepicker",
    "wheelpicker",
    "wheelview",
    "countdown",
    "counttimer",
    "stopwatch",
    "chronometer",
    "timerpicker",
    "alarmedit",
    "alarmsetting",
)

private val CLOCK_ICON_DRAW_CALLERS = listOf(
    "bottomnavigation",
    "navigationbar",
    "navigationrail",
    "tablayout",
    "iconview",
    "iconfont",
    "materialicon",
)

private const val CLOCK_UNKNOWN_TEXT_SIZE_THRESHOLD_SP = 28f

internal fun containsPrivateUseGlyph(text: CharSequence?): Boolean {
    if (text.isNullOrEmpty()) return false
    var index = 0
    while (index < text.length) {
        val codePoint = Character.codePointAt(text, index)
        if (
            codePoint in 0xE000..0xF8FF ||
            codePoint in 0xF0000..0xFFFFD ||
            codePoint in 0x100000..0x10FFFD
        ) {
            return true
        }
        index += Character.charCount(codePoint)
    }
    return false
}

internal fun shouldPreserveClockTextTypeface(text: CharSequence?, familyName: String?): Boolean {
    if (containsPrivateUseGlyph(text)) return true
    val family = familyName?.trim()?.lowercase().orEmpty()
    if (family.isEmpty()) return false
    return CLOCK_PROTECTED_FONT_MARKERS.any(family::contains)
}

/**
 * Decides whether the clock's broad Paint Typeface replacement must be rolled back.
 *
 * Some HyperOS builds hide both icon-font and timer-number family names. Treating every unknown
 * custom Paint as an icon fixed navigation glyphs but also restored the stock Mitype wheel digits.
 * Caller hints and text size separate those two paths without touching every draw operation.
 */
internal fun shouldPreserveClockPaintTypeface(
    familyName: String?,
    systemDefault: Boolean,
    textSizeSp: Float?,
    callerClassNames: List<String>,
): Boolean {
    if (systemDefault) return false

    val family = familyName?.trim()?.lowercase().orEmpty()
    if (family.isNotEmpty()) {
        if (CLOCK_PROTECTED_FONT_MARKERS.any(family::contains)) return true
        if (CLOCK_TEXT_FONT_MARKERS.any(family::contains)) return false
        if (family in CLOCK_GENERIC_TEXT_FAMILIES) return false
    }

    val callers = callerClassNames.joinToString("|").lowercase()
    if (CLOCK_TEXT_DRAW_CALLERS.any(callers::contains)) return false
    if (CLOCK_ICON_DRAW_CALLERS.any(callers::contains)) return true

    // Large anonymous Paints in Clock are timer/stopwatch/world-clock text. Small anonymous Paints
    // are conservatively preserved because OEM icon glyphs commonly have no readable family name.
    if (textSizeSp != null && textSizeSp >= CLOCK_UNKNOWN_TEXT_SIZE_THRESHOLD_SP) return false
    return true
}
