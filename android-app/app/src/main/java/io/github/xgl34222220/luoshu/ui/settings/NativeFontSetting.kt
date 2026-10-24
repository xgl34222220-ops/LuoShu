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
    state.activeEnabled -> "已开启，但洛书字体尚未确认生效，本次开机已自动让出"
    else -> "已关闭"
}
