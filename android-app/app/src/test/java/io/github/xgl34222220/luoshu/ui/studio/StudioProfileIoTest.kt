package io.github.xgl34222220.luoshu.ui.studio

import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.MixSlot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StudioProfileIoTest {
    private val fonts = listOf(
        font("cjk", "中文字体"),
        font("latin", "Latin Font", variable = true),
        font("digit", "Digit Font"),
    )

    @Test
    fun profileRoundTripKeepsFamiliesWeightsAndAxes() {
        val state = FontStudioUiState(
            slots = listOf(
                slot(MixSlot.Cjk, fonts[0], 430, mapOf("wght" to 430f)),
                slot(MixSlot.Latin, fonts[1], 510, mapOf("wght" to 510f, "wdth" to 92f)),
                slot(MixSlot.Digit, fonts[2], 620, mapOf("wght" to 620f)),
            ),
            fonts = fonts,
            hasFonts = true,
        )

        val parsed = parseStudioProfile(encodeStudioProfile(state), fonts)

        assertTrue(parsed.valid)
        assertEquals("latin", parsed.profile?.slots?.get(MixSlot.Latin)?.fontId)
        assertEquals(510, parsed.profile?.slots?.get(MixSlot.Latin)?.weight)
        assertEquals(92f, parsed.profile?.slots?.get(MixSlot.Latin)?.axes?.get("wdth"))
    }

    @Test
    fun missingFamilyRejectsWholeImport() {
        val state = FontStudioUiState(
            slots = listOf(
                slot(MixSlot.Cjk, fonts[0], 400),
                slot(MixSlot.Latin, fonts[1], 400),
                slot(MixSlot.Digit, fonts[2], 400),
            ),
            fonts = fonts,
        )

        val parsed = parseStudioProfile(encodeStudioProfile(state), fonts.dropLast(1))

        assertFalse(parsed.valid)
        assertTrue(parsed.errors.any { it.contains("Digit Font") })
    }

    @Test
    fun malformedJsonIsRejected() {
        val parsed = parseStudioProfile("{not-json", fonts)

        assertFalse(parsed.valid)
        assertTrue(parsed.errors.first().contains("JSON"))
    }

    private fun slot(
        slot: MixSlot,
        font: FontItem,
        weight: Int,
        axes: Map<String, Float> = mapOf("wght" to weight.toFloat()),
    ) = StudioSlotUiState(
        slot = slot,
        title = slot.name,
        subtitle = "",
        sample = "",
        font = font,
        weight = weight,
        axes = axes,
    )

    private fun font(id: String, name: String, variable: Boolean = false) = FontItem(
        id = id,
        name = name,
        format = "TTF",
        size = "1 MB",
        date = "2026-07-24",
        variable = variable,
        valid = true,
        error = "",
        weights = if (variable) listOf("variable") else listOf("regular"),
    )
}
