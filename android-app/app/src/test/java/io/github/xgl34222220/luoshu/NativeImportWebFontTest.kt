package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeImportWebFontTest {
    @Test
    fun webFontsAndArchivesAreAcceptedByThePicker() {
        for (extension in listOf("ttf", "otf", "ttc", "otc", "woff", "woff2", "zip")) {
            assertTrue(extension, extension in ALLOWED_IMPORT_EXTENSIONS)
        }
        assertFalse("eot" in ALLOWED_IMPORT_EXTENSIONS)
        assertFalse("svg" in ALLOWED_IMPORT_EXTENSIONS)
    }

    @Test
    fun webFontConversionGetsMoreTimeThanPlainFonts() {
        assertEquals(60_000L, nativeImportTimeoutMs("ttf"))
        assertEquals(120_000L, nativeImportTimeoutMs("woff"))
        assertEquals(120_000L, nativeImportTimeoutMs("woff2"))
        assertEquals(180_000L, nativeImportTimeoutMs("zip"))
    }
}
