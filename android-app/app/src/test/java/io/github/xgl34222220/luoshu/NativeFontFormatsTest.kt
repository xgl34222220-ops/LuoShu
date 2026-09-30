package io.github.xgl34222220.luoshu

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeFontFormatsTest {
    @Test fun allBackendEntryFormatsAreAccepted() {
        assertEquals(setOf("ttf", "otf", "ttc", "otc", "woff", "woff2", "zip"), NativeFontFormats.importExtensions)
        assertFalse("apk" in NativeFontFormats.importExtensions)
        assertFalse("svg" in NativeFontFormats.importExtensions)
    }
    @Test fun conversionBudgetExceedsNativeDecoderDeadline() {
        for (extension in listOf("woff", "woff2", "otc", "ttc", "zip")) {
            assertTrue(NativeFontFormats.importTimeoutMs(extension) > 90_000L)
        }
        assertEquals(180_000L, NativeFontFormats.importTimeoutMs("WOFF2"))
        assertEquals(60_000L, NativeFontFormats.importTimeoutMs("ttf"))
    }
    @Test fun pendingDefaultDoesNotClaimItAlreadyTookEffect() {
        val state = ModuleSnapshot(activeFont = "default", effectiveFont = "OldFont", fontEffectState = "pending-reboot")
        assertEquals("系统默认字体（等待完整重启）", state.effectiveLabel)
    }
    @Test fun verifiedDefaultAndFailedRollbackRemainDistinct() {
        assertEquals("系统默认字体", ModuleSnapshot(activeFont = "default", effectiveFont = "default", fontEffectState = "system").effectiveLabel)
        assertTrue(ModuleSnapshot(activeFont = "default", effectiveFont = "OldFont", rollbackPending = true, rollbackTargetFont = "OldFont").effectiveLabel.contains("验证失败"))
    }
}
