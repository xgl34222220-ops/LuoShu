package io.github.xgl34222220.luoshu.ui.settings

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeFontSettingTest {
    @Test
    fun commandsUseTheMainModuleBridgeAndOnlyTheEnabledKey() {
        assertEquals("sh '/data/adb/modules/LuoShu/common/app_bridge.sh' native_font_status", nativeFontStatusCommand())
        assertEquals("sh '/data/adb/modules/LuoShu/common/app_bridge.sh' native_font_set enabled 1", nativeFontSetCommand(true))
        assertEquals("sh '/data/adb/modules/LuoShu/common/app_bridge.sh' native_font_set enabled 0", nativeFontSetCommand(false))
    }

    @Test
    fun parsesBridgeStatusAfterRootManagerNoise() {
        val state = parseNativeFontState(
            "noise\n{\"status\":\"ok\",\"data\":{\"enabled\":true,\"verbose\":false,\"library\":true," +
                "\"zygiskLoaded\":true,\"activeEnabled\":true,\"faces\":true,\"legacyConfig\":false}}\n",
        )
        assertTrue(state.enabled)
        assertTrue(state.zygiskLoaded)
        assertEquals("本次开机已生效", nativeFontStatusText(state))
    }

    @Test
    fun defaultsToOffAndExplainsMissingZygisk() {
        val state = parseNativeFontState("{\"status\":\"ok\",\"data\":{\"library\":true}}")
        assertFalse(state.enabled)
        assertTrue(nativeFontStatusText(state).contains("未检测到 Zygisk"))
        assertTrue(nativeFontStatusText(state.copy(enabled = true)).contains("启用 Zygisk 后重启"))
    }

    @Test
    fun pendingRebootAndYieldAreReported() {
        val loaded = NativeFontState(library = true, zygiskLoaded = true)
        assertEquals("设置已保存，重启手机后生效", nativeFontStatusText(loaded.copy(enabled = true)))
        assertTrue(nativeFontStatusText(loaded.copy(enabled = true, activeEnabled = true)).contains("自动让出"))
        assertEquals("已关闭", nativeFontStatusText(loaded))
    }

    @Test
    fun yieldReasonFromBridgeIsShown() {
        val state = parseNativeFontState(
            "{\"status\":\"ok\",\"data\":{\"enabled\":true,\"library\":true,\"zygiskLoaded\":true," +
                "\"activeEnabled\":true,\"faces\":false,\"facesReason\":\"font-not-mounted\"}}",
        )
        assertEquals("font-not-mounted", state.facesReason)
        assertTrue(nativeFontStatusText(state).contains("尚未挂载到系统"))
        assertTrue(nativeFontStatusText(state.copy(facesReason = "verify-failed")).contains("验证失败"))
        assertTrue(nativeFontStatusText(state.copy(facesReason = "odd")).contains("odd"))
    }

    @Test(expected = IllegalStateException::class)
    fun bridgeErrorsAreSurfaced() {
        parseNativeFontState("{\"status\":\"error\",\"message\":\"全局字体增强组件不可用\"}")
    }

    @Test
    fun descriptionCoversRequirementsAndOptOut() {
        listOf("Zygisk", "重启", "图标", "关闭", "默认关闭").forEach { assertTrue(it, NATIVE_FONT_DESCRIPTION.contains(it)) }
    }
}
