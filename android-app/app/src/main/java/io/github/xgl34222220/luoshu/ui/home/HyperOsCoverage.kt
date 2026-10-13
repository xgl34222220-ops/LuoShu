package io.github.xgl34222220.luoshu.ui.home

import io.github.xgl34222220.luoshu.RootShell
import org.json.JSONObject

/**
 * Contract for the HyperOS coverage bridge (common/hyperos_coverage_bridge.sh via app_bridge.sh):
 * theme-store font detection, optional slot groups, seed-XML rewrite, theme takeover and the
 * per-package 未覆盖界面定位. Pure functions so they are unit tested without a device.
 */
internal const val HYPEROS_COVERAGE_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"

internal data class HyperOsThemeState(
    val state: String = "none",
    val files: Int = 0,
    val userFiles: Int = 0,
    val names: List<String> = emptyList(),
    val takeover: Boolean = false,
    val owned: Boolean = false,
) {
    val userThemeActive: Boolean get() = state == "user-theme"
}

internal data class HyperOsCoverageStatus(
    val hyperOs: Boolean = false,
    val miuiEx: Boolean = true,
    val miSansExt: Boolean = true,
    val lockscreenStyles: Boolean = false,
    val sourceXml: Boolean = true,
    val theme: HyperOsThemeState = HyperOsThemeState(),
)

internal data class CoverageFinding(
    val category: String,
    val title: String,
    val action: String,
    val detail: String,
    val files: List<String>,
)

internal data class CoverageLocateResult(
    val packageName: String,
    val verdict: String,
    val findings: List<CoverageFinding>,
    val keptByDesign: List<String>,
)

internal data class CoveragePreset(val label: String, val packageName: String)

/** Common places users report as "not changed", mapped to the process that draws them. */
internal val COVERAGE_PRESETS = listOf(
    CoveragePreset("状态栏 / 通知 / 控制中心 / 锁屏", "com.android.systemui"),
    CoveragePreset("息屏显示（AOD）", "com.miui.aod"),
    CoveragePreset("桌面 / 小部件", "com.miui.home"),
    CoveragePreset("设置", "com.android.settings"),
    CoveragePreset("安全中心", "com.miui.securitycenter"),
    CoveragePreset("天气", "com.miui.weather2"),
    CoveragePreset("微信", "com.tencent.mm"),
)

/** Settings keys accepted by the bridge, in display order. */
internal enum class HyperOsSetting(val key: String, val title: String, val hint: String) {
    MIUI_EX("group:miui_ex", "MiuiEx / Miui 字体", "旧版 MIUI 与主题引擎使用的 MiuiEx-*、Miui-* 文件（默认开）"),
    MISANS_EXT("group:misans_ext", "MiSans 圆体 / 紧凑 / MiLanVF", "MiSansRounded*、MiSansC*、MiLanVF*（默认开）"),
    LOCKSCREEN("group:lockscreen_styles", "锁屏 / 息屏 / 小部件样式字体",
        "Interscaled、C800、Qinghe、ChamberiDisplay、DelaGothicOne 等设计样式字体（默认关，开启会改变这些样式的设计字形；等宽样式始终保留原厂）"),
    SOURCE_XML("xml", "改写 HyperOS 字体配置 XML",
        "覆盖 hyper/miui 种子 XML、fonts_customization.xml；校验失败自动整体回退原厂（默认开）"),
    THEME_TAKEOVER("theme_takeover", "接管主题商店字体",
        "检测到主题商店字体时，开机早期把 /data/system/theme/fonts 下全部字体只读替换为洛书字体；关闭或卸载即恢复（默认关）"),
}

internal fun HyperOsCoverageStatus.valueOf(setting: HyperOsSetting): Boolean = when (setting) {
    HyperOsSetting.MIUI_EX -> miuiEx
    HyperOsSetting.MISANS_EXT -> miSansExt
    HyperOsSetting.LOCKSCREEN -> lockscreenStyles
    HyperOsSetting.SOURCE_XML -> sourceXml
    HyperOsSetting.THEME_TAKEOVER -> theme.takeover
}

internal fun HyperOsCoverageStatus.with(setting: HyperOsSetting, value: Boolean): HyperOsCoverageStatus = when (setting) {
    HyperOsSetting.MIUI_EX -> copy(miuiEx = value)
    HyperOsSetting.MISANS_EXT -> copy(miSansExt = value)
    HyperOsSetting.LOCKSCREEN -> copy(lockscreenStyles = value)
    HyperOsSetting.SOURCE_XML -> copy(sourceXml = value)
    HyperOsSetting.THEME_TAKEOVER -> copy(theme = theme.copy(takeover = value))
}

private val PACKAGE_PATTERN = Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+(:[A-Za-z0-9_.]+)?$")

internal fun isValidCoveragePackage(value: String): Boolean = PACKAGE_PATTERN.matches(value.trim())

internal fun hyperOsCoverageStatusCommand(): String =
    "sh ${RootShell.quote(HYPEROS_COVERAGE_BRIDGE)} hyperos_coverage_status"

internal fun hyperOsSettingCommand(setting: HyperOsSetting, enabled: Boolean): String =
    "sh ${RootShell.quote(HYPEROS_COVERAGE_BRIDGE)} hyperos_coverage_set ${RootShell.quote(setting.key)} ${if (enabled) 1 else 0}"

internal fun coverageLocateCommand(packageName: String): String {
    val trimmed = packageName.trim()
    require(isValidCoveragePackage(trimmed)) { "包名格式不正确" }
    return "sh ${RootShell.quote(HYPEROS_COVERAGE_BRIDGE)} coverage_locate ${RootShell.quote(trimmed)}"
}

/** The bridge prints one JSON line; tolerate root-manager noise before it. */
internal fun bridgeJson(raw: String): JSONObject {
    val trimmed = raw.trim()
    return runCatching { JSONObject(trimmed) }.getOrElse {
        JSONObject(trimmed.lineSequence().lastOrNull { it.trim().startsWith("{") } ?: trimmed)
    }
}

private fun bridgeData(raw: String): JSONObject {
    val json = bridgeJson(raw)
    if (json.optString("status") != "ok") {
        throw IllegalStateException(json.optString("message").ifBlank { "HyperOS 覆盖组件没有返回结果" })
    }
    return json.optJSONObject("data") ?: throw IllegalStateException("HyperOS 覆盖组件返回格式不正确")
}

internal fun parseHyperOsCoverageStatus(raw: String): HyperOsCoverageStatus {
    val data = bridgeData(raw)
    val groups = data.optJSONObject("groups") ?: JSONObject()
    val theme = data.optJSONObject("theme") ?: JSONObject()
    return HyperOsCoverageStatus(
        hyperOs = data.optBoolean("hyperos", false),
        miuiEx = groups.optBoolean("miui_ex", true),
        miSansExt = groups.optBoolean("misans_ext", true),
        lockscreenStyles = groups.optBoolean("lockscreen_styles", false),
        sourceXml = data.optBoolean("sourceXml", true),
        theme = HyperOsThemeState(
            state = theme.optString("state", "none").ifBlank { "none" },
            files = theme.optInt("files", 0),
            userFiles = theme.optInt("userFiles", 0),
            names = theme.optString("names").split(';').map { it.trim() }.filter { it.isNotEmpty() },
            takeover = theme.optBoolean("takeover", false),
            owned = theme.optBoolean("owned", false),
        ),
    )
}

internal fun parseCoverageLocate(raw: String): CoverageLocateResult {
    val data = bridgeData(raw)
    val findings = data.optJSONArray("findings")
    val parsed = buildList {
        if (findings != null) {
            for (index in 0 until findings.length()) {
                val item = findings.optJSONObject(index) ?: continue
                val files = item.optJSONArray("files")
                add(
                    CoverageFinding(
                        category = item.optString("category"),
                        title = item.optString("title"),
                        action = item.optString("action"),
                        detail = item.optString("detail"),
                        files = buildList {
                            if (files != null) for (i in 0 until files.length()) add(files.optString(i))
                        }.filter { it.isNotBlank() },
                    ),
                )
            }
        }
    }
    val kept = data.optJSONArray("keptByDesign")
    return CoverageLocateResult(
        packageName = data.optString("package"),
        verdict = data.optString("verdict"),
        findings = parsed,
        keptByDesign = buildList { if (kept != null) for (i in 0 until kept.length()) add(kept.optString(i)) },
    )
}

/** Strong Home hint while a theme-store font owns the theme route and LuoShu is not taking it over. */
internal fun themeWarningText(theme: HyperOsThemeState): String? = when {
    !theme.userThemeActive -> null
    theme.takeover && theme.owned -> null
    theme.takeover -> "已开启接管主题商店字体，重启后生效。"
    else -> "检测到主题商店字体，它会接管系统界面与网页的默认字体，洛书在这些位置不会生效。" +
        "请在主题商店把字体切回“默认/MiSans”后重启，或在 HyperOS 覆盖设置中开启“接管主题商店字体”。"
}

internal fun settingChangeMessage(setting: HyperOsSetting): String = when (setting) {
    HyperOsSetting.THEME_TAKEOVER -> "已保存，重启后生效。"
    else -> "已保存，重新应用当前字体并重启后生效。"
}

internal val COVERAGE_SCOPE_NOTE =
    "微信、QQ、支付宝等应用内嵌字体与 Chrome 网页字体不在系统字体覆盖范围内；洛书主模块不做 Hook。"
