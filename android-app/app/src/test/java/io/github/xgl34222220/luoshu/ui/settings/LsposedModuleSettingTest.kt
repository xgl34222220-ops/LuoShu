package io.github.xgl34222220.luoshu.ui.settings

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LsposedModuleSettingTest {
    @Test
    fun inactiveTellsUserToEnableLuoShuAndPickScope() {
        val text = lsposedModuleStatusText(LsposedModuleState(activated = false))
        assertTrue(text.contains("在 LSPosed 中启用洛书并勾选作用域"))
        assertFalse(text.contains("伴随"))
    }

    @Test
    fun activeWithLegacyCompanionSuggestsUninstall() {
        val text = lsposedModuleStatusText(LsposedModuleState(activated = true, legacyCompanion = true))
        assertTrue(text.contains("已激活"))
        assertTrue(text.contains("卸载"))
    }
}
