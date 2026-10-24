package io.github.xgl34222220.luoshu.ui.settings

import io.github.xgl34222220.luoshu.RootShell
import org.json.JSONObject

/** 全局字体增强（Zygisk）：主模块 config/native-font.conf 的开关状态与本次开机的加载情况。 */
internal data class NativeFontState(
    val enabled: Boolean = false,
    val library: Boolean = false,
    val zygiskLoaded: Boolean = false,
    val activeEnabled: Boolean = false,
    val faces: Boolean = false,
    val facesReason: String = "",
    val legacyConfig: Boolean = false,
)

internal const val NATIVE_FONT_BRIDGE = "/data/adb/modules/LuoShu/common/app_bridge.sh"

internal const val NATIVE_FONT_TITLE = "全局字体增强（Zygisk）"

internal const val NATIVE_FONT_DESCRIPTION =
    "让 App 自带的正文字体也显示为洛书字体。需要 Root 管理器已启用 Zygisk（Magisk 内置 Zygisk、" +
        "ZygiskNext 或 ReZygisk）；修改后重启手机生效。图标、等宽和彩色字体会自动放行，" +
        "洛书字体未生效时自动让出。遇到显示异常或闪退可随时关闭。默认关闭。"

internal fun nativeFontStatusCommand(): String =
    "sh ${RootShell.quote(NATIVE_FONT_BRIDGE)} native_font_status"

internal fun nativeFontSetCommand(enabled: Boolean): String =
    "sh ${RootShell.quote(NATIVE_FONT_BRIDGE)} native_font_set enabled ${if (enabled) 1 else 0}"

/** The bridge prints one JSON line; tolerate root-manager noise before it. */
internal fun parseNativeFontState(raw: String): NativeFontState {
    val trimmed = raw.trim()
    val json = runCatching { JSONObject(trimmed) }.getOrElse {
        JSONObject(trimmed.lineSequence().lastOrNull { it.trim().startsWith("{") } ?: "{}")
    }
    if (json.optString("status") != "ok") {
        throw IllegalStateException(json.optString("message").ifBlank { "全局字体增强组件没有返回结果" })
    }
    val data = json.optJSONObject("data") ?: throw IllegalStateException("全局字体增强组件返回格式不正确")
    return NativeFontState(
        enabled = data.optBoolean("enabled", false),
        library = data.optBoolean("library", false),
        zygiskLoaded = data.optBoolean("zygiskLoaded", false),
        activeEnabled = data.optBoolean("activeEnabled", false),
        faces = data.optBoolean("faces", false),
        facesReason = data.optString("facesReason", ""),
        legacyConfig = data.optBoolean("legacyConfig", false),
    )
}

/** One status line under the switch: what is true for this boot, and whether a reboot is pending. */
internal fun nativeFontStatusText(state: NativeFontState): String = when {
    !state.library -> "当前模块未包含本机架构的 Zygisk 库"
    !state.zygiskLoaded && state.enabled -> "本次开机未检测到 Zygisk 加载：请在 Root 管理器中启用 Zygisk 后重启"
    !state.zygiskLoaded -> "本次开机未检测到 Zygisk 加载（未启用 Zygisk 时对系统没有任何影响）"
    state.enabled != state.activeEnabled -> "设置已保存，重启手机后生效"
    state.activeEnabled && state.faces -> "本次开机已生效"
    state.activeEnabled -> "已开启，但本次开机已自动让出：${nativeFontYieldReason(state.facesReason)}"
    else -> "已关闭"
}

/** state.conf reason= written by native_font.sh prepare when no LuoShu face was compiled. */
internal fun nativeFontYieldReason(reason: String): String = when (reason) {
    "no-active-font" -> "当前使用系统默认字体"
    "reboot-required" -> "字体切换待重启生效"
    "payload-rebuild-pending" -> "字体负载待重建"
    "verify-failed" -> "上次字体加载验证失败"
    "no-luoshu-faces" -> "模块内没有洛书正文字体文件"
    "font-not-mounted" -> "洛书字体尚未挂载到系统（稍后会自动重试）"
    "faces-build-failed" -> "字体表生成失败"
    "config-build-failed" -> "排除名单或配置生成失败"
    "java-font-off" -> "App 字体替换已关闭"
    "module-disabled" -> "洛书模块已禁用"
    "" -> "洛书字体尚未确认生效"
    else -> "洛书字体尚未确认生效（$reason）"
}
