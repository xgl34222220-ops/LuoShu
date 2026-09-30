package io.github.xgl34222220.luoshu

/** Entry-point formats; imported web/collection fonts are normalized by the backend. */
internal object NativeFontFormats {
    val importExtensions = setOf("ttf", "otf", "ttc", "otc", "woff", "woff2", "zip")
    const val importDescription = "TTF、OTF、TTC、OTC、WOFF、WOFF2 和 ZIP"

    fun importTimeoutMs(extension: String): Long = when (extension.lowercase()) {
        "zip", "ttc", "otc", "woff", "woff2" -> 180_000L
        else -> 60_000L
    }
}
