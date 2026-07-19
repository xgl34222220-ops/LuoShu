package io.github.xgl34222220.luoshu.ui.appearance

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppearanceSettingsTest {
    @Test
    fun uiStyleStorageFallsBackToMiuix() {
        assertEquals(UiStyle.MATERIAL, UiStyle.fromStorage("material"))
        assertEquals(UiStyle.MIUIX, UiStyle.fromStorage("MIUIX"))
        assertEquals(UiStyle.MIUIX, UiStyle.fromStorage("unknown"))
        assertEquals(UiStyle.MIUIX, UiStyle.fromStorage(null))
    }

    @Test
    fun themeModeStorageSupportsAllThreeModes() {
        assertEquals(ThemeMode.SYSTEM, ThemeMode.fromStorage("system"))
        assertEquals(ThemeMode.LIGHT, ThemeMode.fromStorage("LIGHT"))
        assertEquals(ThemeMode.DARK, ThemeMode.fromStorage("dark"))
        assertEquals(ThemeMode.SYSTEM, ThemeMode.fromStorage("invalid"))
    }

    @Test
    fun legacyKolorNamesAreMappedToCurrentChoices() {
        assertEquals(KolorStyle.SOFT, KolorStyle.fromStorage(null))
        assertEquals(KolorStyle.NEUTRAL, KolorStyle.fromStorage("monochrome"))
        assertEquals(KolorStyle.VIBRANT, KolorStyle.fromStorage("expressive"))
        assertEquals(KolorStyle.VIBRANT, KolorStyle.fromStorage("content"))
    }

    @Test
    fun invalidAccentFallsBackToLuoShuBlue() {
        val normalized = AppearanceSettings(seedArgb = 0x12345678).normalized()
        assertEquals(AccentOptions.first().argb, normalized.seedArgb)
        assertEquals("luoshu", normalized.accent.id)
    }

    @Test
    fun blurCannotRemainEnabledWhenGlassIsDisabled() {
        val normalized = AppearanceSettings(
            glassEnabled = false,
            blurEnabled = true,
        ).normalized()

        assertFalse(normalized.glassEnabled)
        assertFalse(normalized.blurEnabled)
    }

    @Test
    fun validMaterialSettingsArePreserved() {
        val source = AppearanceSettings(
            uiStyle = UiStyle.MATERIAL,
            themeMode = ThemeMode.DARK,
            seedArgb = AccentOptions.last().argb,
            kolorStyle = KolorStyle.NEUTRAL,
            monetEnabled = false,
            amoledBlack = true,
            glassEnabled = true,
            blurEnabled = true,
            floatingDock = false,
        )

        val normalized = source.normalized()
        assertEquals(source, normalized)
        assertTrue(normalized.blurEnabled)
    }
}
