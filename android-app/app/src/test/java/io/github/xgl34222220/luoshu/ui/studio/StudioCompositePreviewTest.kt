package io.github.xgl34222220.luoshu.ui.studio

import io.github.xgl34222220.luoshu.MixSlot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StudioCompositePreviewTest {
    @Test
    fun quickPresetsHaveStableUniqueIds() {
        assertEquals(4, studioQuickPresets.size)
        assertEquals(studioQuickPresets.size, studioQuickPresets.map { it.id }.toSet().size)
        assertTrue(studioQuickPresets.all { it.id.isNotBlank() && it.label.isNotBlank() })
    }

    @Test
    fun numberPresetOnlyEmphasizesDigitRole() {
        val preset = studioQuickPresets.first { it.id == "numbers" }

        assertEquals(400, preset.weightFor(MixSlot.Cjk))
        assertEquals(400, preset.weightFor(MixSlot.Latin))
        assertEquals(650, preset.weightFor(MixSlot.Digit))
    }

    @Test
    fun headlinePresetKeepsAllRolesAligned() {
        val preset = studioQuickPresets.first { it.id == "headline" }

        MixSlot.entries.forEach { slot ->
            assertEquals(600, preset.weightFor(slot))
        }
    }
}
