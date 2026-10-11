package io.github.xgl34222220.luoshu.ui.home

import io.github.xgl34222220.luoshu.ModuleSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ForeignFontModulesTest {
    @Test
    fun parsesIdsWithNamesAndKeepsIdsWithoutNames() {
        val modules = parseForeignFontModules(
            "mfga,ufs,bare",
            "mfga:Make Fonts Great Again|ufs:Unicode: Font Set",
        )

        assertEquals(listOf("mfga", "ufs", "bare"), modules.map { it.id })
        assertEquals("Make Fonts Great Again（mfga）", modules[0].label)
        assertEquals("Unicode: Font Set（ufs）", modules[1].label)
        assertEquals("bare", modules[2].label)
    }

    @Test
    fun emptyFieldsMeanNoForeignModules() {
        assertTrue(parseForeignFontModules("", "").isEmpty())
        assertTrue(parseForeignFontModules(" , ", "x:y").isEmpty())
    }

    @Test
    fun verifiedSnapshotCarriesWarningAndFontLoaderIsOnlyAHint() {
        val state = ModuleSnapshot(
            loading = false,
            rootGranted = true,
            installed = true,
            foreignFontModules = "mfga,ufs",
            foreignFontModuleNames = "mfga:MFGA|ufs:UFS",
            fontLoaderPresent = true,
        ).toHomeUiState()

        assertEquals(2, state.foreignFontModules.size)
        assertTrue(state.fontLoaderPresent)
        assertEquals("检测到 2 个其他字体模块，可能覆盖洛书效果", foreignFontWarningTitle(state.foreignFontModules.size))
        assertTrue(foreignFontWarningHint(true).contains("FontLoader"))
        assertFalse(foreignFontWarningHint(false).contains("FontLoader"))
    }

    @Test
    fun cachedSnapshotDoesNotShowStaleWarning() {
        val state = ModuleSnapshot(
            statusCached = true,
            installed = true,
            foreignFontModules = "mfga",
        ).toHomeUiState()

        assertTrue(state.foreignFontModules.isEmpty())
    }
}
