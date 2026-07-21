package io.github.xgl34222220.luoshu.hook

import kotlin.math.roundToInt

internal val QQ_PACKAGES = setOf("com.tencent.mobileqq", "com.tencent.tim")

private val QQ_PROTECTED_FONT_MARKERS = listOf(
    "emoji",
    "symbol",
    "glyph",
    "icon",
    "materialicon",
    "materialsymbol",
    "dingbat",
    "barcode",
    "qrcode",
    "monospace",
    "robotomono",
    "code",
)

private val QQ_REPLACEABLE_FONT_MARKERS = listOf(
    "sans",
    "sansserif",
    "default",
    "miui",
    "misans",
    "mipro",
    "roboto",
    "sourcesans",
    "tencent",
)

private const val QQ_LABEL_MAX_TEXT_SIZE_SP = 14.5f
private const val QQ_LABEL_MAX_HEIGHT_DP = 32f
private const val QQ_LABEL_MAX_TEXT_LENGTH = 28
private const val QQ_LABEL_MIN_SCALE = 0.72f

internal fun isQqUiProcess(packageName: String, processName: String): Boolean =
    packageName in QQ_PACKAGES && processName == packageName

internal fun isHyperOsFamily(
    manufacturer: String?,
    brand: String?,
    miOsVersionName: String?,
    miuiVersionCode: String?,
): Boolean {
    if (!miOsVersionName.isNullOrBlank() || !miuiVersionCode.isNullOrBlank()) return true
    val identity = "${manufacturer.orEmpty()} ${brand.orEmpty()}".lowercase()
    return listOf("xiaomi", "redmi", "poco").any(identity::contains)
}

internal fun shouldPreserveQqTypeface(text: CharSequence?, familyName: String?): Boolean {
    if (containsPrivateUseGlyph(text)) return true
    val family = normalizeQqFamily(familyName.orEmpty())
    return family.isNotEmpty() && QQ_PROTECTED_FONT_MARKERS.any(family::contains)
}

internal fun isReplaceableQqFamily(familyName: String?): Boolean {
    val family = normalizeQqFamily(familyName.orEmpty())
    if (family.isEmpty()) return true
    if (QQ_PROTECTED_FONT_MARKERS.any(family::contains)) return false
    return QQ_REPLACEABLE_FONT_MARKERS.any(family::contains)
}

internal fun isCompactQqLabelCandidate(
    textSizeSp: Float,
    heightDp: Float,
    lineCount: Int,
    textLength: Int,
    editable: Boolean,
): Boolean {
    if (editable || lineCount != 1 || textLength !in 1..QQ_LABEL_MAX_TEXT_LENGTH) return false
    if (!textSizeSp.isFinite() || !heightDp.isFinite()) return false
    return textSizeSp in 7f..QQ_LABEL_MAX_TEXT_SIZE_SP && heightDp in 12f..QQ_LABEL_MAX_HEIGHT_DP
}

/**
 * Returns a smaller text size only when the actual font metrics exceed the label's content box.
 * This avoids blanket scaling and keeps normal QQ text untouched.
 */
internal fun fittedQqLabelTextSizePx(
    currentTextSizePx: Float,
    availableHeightPx: Int,
    fontHeightPx: Int,
): Float? {
    if (!currentTextSizePx.isFinite() || currentTextSizePx <= 0f) return null
    if (availableHeightPx <= 0 || fontHeightPx <= availableHeightPx) return null
    val scale = ((availableHeightPx - 1f) / fontHeightPx.toFloat()).coerceIn(QQ_LABEL_MIN_SCALE, 1f)
    val target = currentTextSizePx * scale
    return target.takeIf { it < currentTextSizePx * 0.995f }
}

/** Estimates metrics at the original size after a recycled label has already been scaled once. */
internal fun originalQqLabelFontHeightPx(
    currentFontHeightPx: Int,
    currentTextSizePx: Float,
    originalTextSizePx: Float,
): Int {
    if (
        currentFontHeightPx <= 0 ||
        !currentTextSizePx.isFinite() ||
        currentTextSizePx <= 0f ||
        !originalTextSizePx.isFinite() ||
        originalTextSizePx <= 0f
    ) {
        return currentFontHeightPx
    }
    return (currentFontHeightPx * (originalTextSizePx / currentTextSizePx))
        .roundToInt()
        .coerceAtLeast(1)
}

private fun normalizeQqFamily(value: String): String = buildString(value.length) {
    value.lowercase().forEach { character ->
        if (character.isLetterOrDigit()) append(character)
    }
}
