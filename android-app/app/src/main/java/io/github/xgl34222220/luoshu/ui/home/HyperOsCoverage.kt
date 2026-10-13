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
    /** Files in the theme dir that are LuoShu's own clone/payload (never a theme-store font). */
    val luoshuFiles: Int = 0,
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
            luoshuFiles = theme.optInt("luoshuFiles", 0),
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

// --- 选择应用定位 / 一键扫描 ----------------------------------------------------------------------

/** One installed app (user or system) offered by the locator picker. */
internal data class CoverageApp(
    val packageName: String,
    val label: String,
    val system: Boolean,
)

/**
 * Root fallback for the picker: `pm list packages` lines ("package:com.x"), used when the
 * PackageManager list is filtered (HyperOS "获取应用列表" permission) or incomplete.
 */
internal const val COVERAGE_PACKAGE_LIST_COMMAND = "pm list packages 2>/dev/null || cmd package list packages 2>/dev/null"

internal fun parsePmPackageList(raw: String): List<String> = raw.lineSequence()
    .map { it.trim() }
    .filter { it.startsWith("package:") }
    .map { it.removePrefix("package:").substringBefore('=').trim() }
    .filter { isValidCoveragePackage(it) }
    .distinct()
    .toList()

/** PackageManager entries win (label/icon); root-only packages are added by name. */
internal fun mergeCoverageApps(fromPackageManager: List<CoverageApp>, fromRoot: List<String>): List<CoverageApp> {
    val byPackage = LinkedHashMap<String, CoverageApp>()
    fromPackageManager.forEach { byPackage[it.packageName] = it }
    fromRoot.forEach { name -> byPackage.getOrPut(name) { CoverageApp(name, name, system = true) } }
    return byPackage.values.sortedBy { (if (it.system) "1" else "0") + it.label.lowercase() + "\u0000" + it.packageName }
}

/** Search by label or package name, case-insensitive. */
internal fun filterCoverageApps(apps: List<CoverageApp>, query: String): List<CoverageApp> {
    val needle = query.trim().lowercase()
    return if (needle.isEmpty()) apps
    else apps.filter { it.label.lowercase().contains(needle) || it.packageName.lowercase().contains(needle) }
}

internal data class CoverageScanItem(
    val packageName: String,
    val process: String,
    val verdict: String,
    val title: String,
    val fixes: List<HyperOsSetting>,
    val reasons: List<String>,
)

internal data class CoverageScanResult(
    val verdict: String,
    val scanned: Int,
    val covered: Int,
    val items: List<CoverageScanItem>,
    val fixes: List<HyperOsSetting>,
    val truncated: Boolean,
    val weightLoss: Boolean,
) {
    val fixable: List<CoverageScanItem> get() = items.filter { it.fixes.isNotEmpty() }
}

internal fun coverageScanCommand(): String = "sh ${RootShell.quote(HYPEROS_COVERAGE_BRIDGE)} coverage_scan"

internal fun hyperOsSettingForKey(key: String): HyperOsSetting? = HyperOsSetting.entries.firstOrNull { it.key == key }

private fun org.json.JSONArray?.strings(): List<String> = buildList {
    if (this@strings != null) for (i in 0 until this@strings.length()) add(this@strings.optString(i))
}.filter { it.isNotBlank() }

internal fun parseCoverageScan(raw: String): CoverageScanResult {
    val data = bridgeData(raw)
    val items = data.optJSONArray("items")
    val parsed = buildList {
        if (items != null) {
            for (index in 0 until items.length()) {
                val item = items.optJSONObject(index) ?: continue
                add(
                    CoverageScanItem(
                        packageName = item.optString("package"),
                        process = item.optString("process").ifBlank { item.optString("package") },
                        verdict = item.optString("verdict"),
                        title = item.optString("title"),
                        fixes = item.optJSONArray("fixes").strings().mapNotNull(::hyperOsSettingForKey),
                        reasons = item.optJSONArray("reasons").strings(),
                    ),
                )
            }
        }
    }
    return CoverageScanResult(
        verdict = data.optString("verdict"),
        scanned = data.optInt("scanned", 0),
        covered = data.optInt("covered", 0),
        items = parsed,
        fixes = data.optJSONArray("fixes").strings().mapNotNull(::hyperOsSettingForKey),
        truncated = data.optBoolean("truncated", false),
        weightLoss = data.optBoolean("weightLoss", false),
    )
}

/** Settings a one-tap apply would actually change (already-on switches are skipped). */
internal fun pendingScanFixes(scan: CoverageScanResult, status: HyperOsCoverageStatus): List<HyperOsSetting> =
    scan.fixes.distinct().filter { !status.valueOf(it) }

internal fun coverageScanSummary(scan: CoverageScanResult): String = when {
    scan.verdict == "no-payload" -> "洛书当前没有生效的字体负载，先在字体库应用一款字体并重启。"
    scan.items.isEmpty() -> "已检测 ${scan.scanned} 个正在运行的进程，都在使用洛书字体。"
    else -> "已检测 ${scan.scanned} 个正在运行的进程：${scan.covered} 个已使用洛书字体，" +
        "${scan.items.size} 个没有（可自动处理 ${scan.fixable.size} 个）。"
} + (if (scan.weightLoss) "当前为静态字体，中粗/粗体会显示为常规粗细。" else "") +
    (if (scan.truncated) "进程较多，本次只检测了一部分。" else "")

internal fun scanFixMessage(applied: List<HyperOsSetting>, requested: List<HyperOsSetting>): String {
    if (applied.isEmpty()) return "应用失败，请确认已授予 Root 权限后重试。"
    val names = applied.joinToString("、") { it.title }
    val effect = if (applied.any { it != HyperOsSetting.THEME_TAKEOVER }) "重新应用当前字体并重启后生效。" else "重启后生效。"
    val rest = if (applied.size < requested.size) "其余设置未能保存，请重试。" else ""
    return "已打开：$names。$rest$effect"
}
