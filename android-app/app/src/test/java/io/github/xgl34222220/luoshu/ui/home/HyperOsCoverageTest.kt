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

    @Test
    fun parsesLuoShuOwnedThemeFilesWithoutWarning() {
        // Real device: theme store on DEFAULT, LuoShu's own route bind on Roboto-Regular.ttf.
        val status = parseHyperOsCoverageStatus(
            """{"status":"ok","data":{"hyperos":true,"theme":{"state":"placeholder","files":1,"userFiles":0,"luoshuFiles":1,"names":"Roboto-Regular.ttf","takeover":false,"owned":false}}}""",
        )
        assertEquals(1, status.theme.luoshuFiles)
        assertFalse(status.theme.userThemeActive)
        assertNull(themeWarningText(status.theme))
    }

    @Test
    fun pmPackageListIsParsedAndMergedBehindPackageManagerEntries() {
        val root = parsePmPackageList(
            """
            package:com.android.systemui
            package:com.miui.aod
            package:/data/app/x.apk=com.bad
            garbage line
            package:com.miui.aod
            """.trimIndent(),
        )
        assertEquals(listOf("com.android.systemui", "com.miui.aod"), root)
        val merged = mergeCoverageApps(
            listOf(CoverageApp("com.tencent.mm", "微信", system = false),
                CoverageApp("com.android.systemui", "系统界面", system = true)),
            root,
        )
        assertEquals(listOf("com.tencent.mm", "com.miui.aod", "com.android.systemui"), merged.map { it.packageName })
        assertEquals("系统界面", merged.first { it.packageName == "com.android.systemui" }.label)
        assertEquals("com.miui.aod", merged.first { it.packageName == "com.miui.aod" }.label)
    }

    @Test
    fun appSearchMatchesLabelOrPackage() {
        val apps = listOf(CoverageApp("com.tencent.mm", "微信", false), CoverageApp("com.android.systemui", "系统界面", true))
        assertEquals(2, filterCoverageApps(apps, "").size)
        assertEquals(listOf("com.tencent.mm"), filterCoverageApps(apps, "微").map { it.packageName })
        assertEquals(listOf("com.android.systemui"), filterCoverageApps(apps, " SYSTEMUI ").map { it.packageName })
    }

    @Test
    fun scanResultMapsFixesToExistingSettings() {
        val scan = parseCoverageScan(
            """{"status":"ok","data":{"schema":"luoshu-coverage-scan-v1","verdict":"ok","scanned":5,"covered":3,
            "items":[{"package":"com.miui.aod","process":"com.miui.aod","pid":"101","verdict":"outside-whitelist","title":"读取了原厂字体","fixes":["group:lockscreen_styles"],"reasons":[]},
                     {"package":"com.example.hidden","process":"com.example.hidden:remote","pid":"102","verdict":"namespace-hidden","title":"看不到模块","fixes":[],"reasons":["看不到模块：在 App Profile 关闭卸载模块"]}],
            "fixes":["group:lockscreen_styles","unknown:key"],"truncated":false,"weightLoss":true}}""",
        )
        assertEquals(listOf(HyperOsSetting.LOCKSCREEN), scan.fixes)
        assertEquals(1, scan.fixable.size)
        assertEquals("com.example.hidden:remote", scan.items.single { it.fixes.isEmpty() }.process)
        assertTrue(scan.weightLoss)
        assertEquals(listOf(HyperOsSetting.LOCKSCREEN), pendingScanFixes(scan, HyperOsCoverageStatus()))
        assertTrue(pendingScanFixes(scan, HyperOsCoverageStatus(lockscreenStyles = true)).isEmpty())
        assertTrue(coverageScanSummary(scan).contains("2 个没有"))
        assertTrue(coverageScanSummary(scan).contains("静态字体"))
        assertEquals("sh '/data/adb/modules/LuoShu/common/app_bridge.sh' coverage_scan", coverageScanCommand())
    }

    @Test
    fun scanFixMessageSaysWhatWasTurnedOn() {
        assertTrue(scanFixMessage(emptyList(), listOf(HyperOsSetting.LOCKSCREEN)).contains("失败"))
        val all = scanFixMessage(listOf(HyperOsSetting.LOCKSCREEN), listOf(HyperOsSetting.LOCKSCREEN))
        assertTrue(all.contains(HyperOsSetting.LOCKSCREEN.title))
        assertTrue(all.contains("重新应用当前字体"))
        assertEquals("已打开：接管主题商店字体。重启后生效。",
            scanFixMessage(listOf(HyperOsSetting.THEME_TAKEOVER), listOf(HyperOsSetting.THEME_TAKEOVER)))
        assertTrue(scanFixMessage(listOf(HyperOsSetting.THEME_TAKEOVER),
            listOf(HyperOsSetting.THEME_TAKEOVER, HyperOsSetting.LOCKSCREEN)).contains("其余设置未能保存"))
    }

    @Test
    fun coverageEntryWorksOnEveryRomWithRomSpecificPresets() {
        val coloros = parseHyperOsCoverageStatus("""{"status":"ok","data":{"hyperos":false,"rom":"coloros"}}""")
        assertEquals("coloros", coloros.rom)
        assertFalse(coloros.hyperOs)
        assertEquals("com.android.launcher", coveragePresetsFor("coloros")[1].packageName)
        assertFalse(coveragePresetsFor("coloros").any { it.packageName.startsWith("com.miui") })
        assertFalse(coveragePresetsFor("other").any { it.packageName.startsWith("com.miui") })
        assertEquals(COVERAGE_PRESETS, coveragePresetsFor("hyperos"))
        assertFalse(coverageEntrySubtitle(coloros).contains("HyperOS"))
        val hyper = parseHyperOsCoverageStatus("""{"status":"ok","data":{"hyperos":true}}""")
        assertEquals("hyperos", hyper.rom)
        assertTrue(coverageEntrySubtitle(hyper).contains("HyperOS 覆盖设置"))
        assertEquals("other", parseHyperOsCoverageStatus("""{"status":"ok","data":{"rom":"weird"}}""").rom)
    }

    @Test
    fun parsesExportResultAndRejectsUnexpectedPaths() {
        assertEquals("sh '/data/adb/modules/LuoShu/common/app_bridge.sh' coverage_export", coverageExportCommand())
        val result = parseCoverageExport(
            """{"status":"ok","data":{"path":"/sdcard/LuoShu/reports/LuoShu-coverage-full-20261013-201500.json","bytes":20480,"issues":3,"processesWithIssues":41,"rom":"coloros"}}""",
        )
        assertEquals(3, result.issues)
        assertTrue(coverageExportSummary(result).contains("41 个进程"))
        assertTrue(coverageExportSummary(result).contains("20 KB"))
        try {
            parseCoverageExport("""{"status":"ok","data":{"path":"/sdcard/other.json"}}""")
            fail("expected error")
        } catch (error: IllegalStateException) {
            assertTrue(error.message!!.contains("路径"))
        }
    }

    @Test
    fun scanItemsCarryFileNames() {
        val scan = parseCoverageScan(
            """{"status":"ok","data":{"verdict":"ok","scanned":2,"covered":1,"items":[{"package":"com.android.launcher","process":"com.android.launcher","verdict":"outside-whitelist","title":"t","fixes":[],"reasons":["r"],"files":["/system/fonts/VendorDisplay-Regular.ttf"]}],"fixes":[]}}""",
        )
        assertEquals(listOf("/system/fonts/VendorDisplay-Regular.ttf"), scan.items.single().files)
    }
}
