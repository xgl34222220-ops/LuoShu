package io.github.xgl34222220.luoshu.ui.studio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StudioPresetStoreTest {
    @Test
    fun presetRoundTripPreservesProfileAndFlags() {
        val item = StoredStudioPreset(
            id = "preset-1",
            name = "日常方案",
            profileRaw = """{"schema":1,"type":"luoshu-studio-profile","slots":{}}""",
            createdAt = 10L,
            updatedAt = 20L,
            lastUsedAt = 30L,
            favorite = true,
        )
        val decoded = decodePresets(encodePresets(listOf(item))).single()
        assertEquals(item.id, decoded.id)
        assertEquals(item.name, decoded.name)
        assertEquals(item.profileRaw, decoded.profileRaw)
        assertEquals(30L, decoded.lastUsedAt)
        assertTrue(decoded.favorite)
    }

    @Test
    fun invalidStoreIsIgnored() {
        assertTrue(decodePresets("not-json").isEmpty())
        assertTrue(decodePresets("""{"schema":99,"presets":[]}""").isEmpty())
    }

    @Test
    fun namesAreSanitizedAndBounded() {
        val value = sanitizePresetName("  我的\n方案   A  ")
        assertEquals("我的 方案 A", value)
        assertTrue(sanitizePresetName("x".repeat(100)).length <= 48)
        assertFalse(sanitizePresetName("   ").isBlank())
    }
}
