package io.github.xgl34222220.luoshu.ui.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class HyperOsCoverageTest {
    @Test
    fun parsesBridgeStatusWithDefaultsAndThemeDetection() {
        val status = parseHyperOsCoverageStatus(
            """
            noise from a root manager
            {"status":"ok","data":{"hyperos":true,"groups":{"miui_ex":true,"misans_ext":false,"lockscreen_styles":true},"sourceXml":false,"theme":{"state":"user-theme","files":3,"userFiles":2,"names":"Roboto-Regular.ttf;Roboto-Bold.ttf","takeover":false,"owned":false}}}
            """.trimIndent(),
        )
        assertTrue(status.hyperOs)
        assertTrue(status.miuiEx)
        assertFalse(status.miSansExt)
        assertTrue(status.lockscreenStyles)
        assertFalse(status.sourceXml)
        assertTrue(status.theme.userThemeActive)
        assertEquals(listOf("Roboto-Regular.ttf", "Roboto-Bold.ttf"), status.theme.names)

        val defaults = parseHyperOsCoverageStatus("""{"status":"ok","data":{"hyperos":false}}""")
        assertEquals(HyperOsCoverageStatus(), defaults)
        assertTrue(defaults.sourceXml)
        assertFalse(defaults.lockscreenStyles)
    }

    @Test
    fun bridgeErrorsSurfaceTheirMessage() {
        try {
            parseHyperOsCoverageStatus("""{"status":"error","message":"HyperOS 覆盖组件不可用"}""")
            fail("expected error")
        } catch (error: IllegalStateException) {
            assertEquals("HyperOS 覆盖组件不可用", error.message)
        }
    }

    @Test
    fun themeWarningOnlyWhileAUserThemeIsNotTakenOver() {
        assertNull(themeWarningText(HyperOsThemeState(state = "none")))
        assertNull(themeWarningText(HyperOsThemeState(state = "placeholder")))
        val warning = themeWarningText(HyperOsThemeState(state = "user-theme"))
        assertNotNull(warning)
        assertTrue(warning!!.contains("主题商店"))
        assertTrue(warning.contains("接管主题商店字体"))
        assertEquals("已开启接管主题商店字体，重启后生效。",
            themeWarningText(HyperOsThemeState(state = "user-theme", takeover = true)))
        assertNull(themeWarningText(HyperOsThemeState(state = "user-theme", takeover = true, owned = true)))
    }

    @Test
    fun parsesLocatorFindingsInOrder() {
        val result = parseCoverageLocate(
            """{"status":"ok","data":{"package":"com.android.systemui","verdict":"theme-takeover","findings":[
              {"category":"theme-takeover","title":"主题商店字体接管了系统字体","action":"切回默认","detail":"d","files":["/data/system/theme/fonts/Roboto-Regular.ttf"]},
              {"category":"outside-whitelist","title":"白名单外","action":"开启分组","detail":"","files":["/system/fonts/C800.ttf（lockscreen_styles 组未开启）"]}
            ],"keptByDesign":["/system/fonts/RobotoMono-Regular.ttf（按设计保留：mono）"]}}""",
        )
        assertEquals("theme-takeover", result.verdict)
        assertEquals(listOf("theme-takeover", "outside-whitelist"), result.findings.map { it.category })
        assertEquals(1, result.findings[1].files.size)
        assertEquals(1, result.keptByDesign.size)
    }

    @Test
    fun commandsQuoteArgumentsAndRejectBadPackages() {
        assertEquals(
            "sh '/data/adb/modules/LuoShu/common/app_bridge.sh' hyperos_coverage_set 'group:lockscreen_styles' 1",
            hyperOsSettingCommand(HyperOsSetting.LOCKSCREEN, true),
        )
        assertTrue(hyperOsSettingCommand(HyperOsSetting.THEME_TAKEOVER, false).endsWith("'theme_takeover' 0"))
        assertTrue(coverageLocateCommand(" com.android.systemui ").endsWith("coverage_locate 'com.android.systemui'"))
        assertTrue(isValidCoveragePackage("com.tencent.mm"))
        assertTrue(isValidCoveragePackage("com.android.systemui:screenshot"))
        for (bad in listOf("", "systemui", "com.x;reboot", "../etc", "com..x", "1com.x")) {
            assertFalse(bad, isValidCoveragePackage(bad))
        }
        try {
            coverageLocateCommand("com.x'; reboot; '")
            fail("expected rejection")
        } catch (_: IllegalArgumentException) {
        }
    }

    @Test
    fun settingsMatchBridgeKeysDefaultsAndMessages() {
        assertEquals(
            listOf("group:miui_ex", "group:misans_ext", "group:lockscreen_styles", "xml", "theme_takeover"),
            HyperOsSetting.entries.map { it.key },
        )
        val defaults = HyperOsCoverageStatus()
        assertTrue(defaults.valueOf(HyperOsSetting.MIUI_EX))
        assertTrue(defaults.valueOf(HyperOsSetting.MISANS_EXT))
        assertFalse(defaults.valueOf(HyperOsSetting.LOCKSCREEN))
        assertTrue(defaults.valueOf(HyperOsSetting.SOURCE_XML))
        assertFalse(defaults.valueOf(HyperOsSetting.THEME_TAKEOVER))
        val changed = defaults.with(HyperOsSetting.THEME_TAKEOVER, true).with(HyperOsSetting.LOCKSCREEN, true)
        assertTrue(changed.theme.takeover)
        assertTrue(changed.lockscreenStyles)
        assertTrue(settingChangeMessage(HyperOsSetting.LOCKSCREEN).contains("重新应用"))
        assertFalse(settingChangeMessage(HyperOsSetting.THEME_TAKEOVER).contains("重新应用"))
        assertTrue(COVERAGE_SCOPE_NOTE.contains("微信"))
        assertTrue(COVERAGE_SCOPE_NOTE.contains("Chrome"))
        assertEquals("com.android.systemui", COVERAGE_PRESETS.first().packageName)
    }
}
