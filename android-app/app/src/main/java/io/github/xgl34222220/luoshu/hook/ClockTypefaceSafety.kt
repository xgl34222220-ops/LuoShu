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

internal fun shouldPreserveClockPaintTypeface(
    familyName: String?,
    systemDefault: Boolean,
): Boolean {
    if (systemDefault) return false
    val family = familyName?.trim()?.lowercase().orEmpty()
    if (family.isEmpty()) return true
    if (CLOCK_PROTECTED_FONT_MARKERS.any(family::contains)) return true
    if (CLOCK_TEXT_FONT_MARKERS.any(family::contains)) return false
    if (family in CLOCK_GENERIC_TEXT_FAMILIES) return false
    return true
}
