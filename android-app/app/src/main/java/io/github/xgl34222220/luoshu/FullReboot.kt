package io.github.xgl34222220.luoshu

import org.json.JSONObject

/**
 * 首页「立即重启」: a complete device reboot through app_bridge.sh `reboot` (full_reboot:
 * `svc power reboot`, then toybox `reboot`, then `setprop sys.powerctl reboot`, all in the
 * foreground of the supervised request). Never a soft restart: only a real boot remounts the font
 * payload before system_server builds its font map.
 */
internal const val FULL_REBOOT_TIMEOUT_MS = 45_000L

internal fun fullRebootCommand(bridge: String): String = "sh ${RootShell.quote(bridge)} reboot"

/** Null while the device is going down; a user-facing message when no reboot path worked. */
internal fun rebootFailureMessage(result: ShellResult): String? {
    if (result.code == 0) return null
    if (result.code == 124) return "重启请求超时，手机没有重启。请长按电源键手动重启。"
    val bridgeMessage = result.stdout.lineSequence().map { it.trim() }.lastOrNull { it.startsWith("{") }
        ?.let { line -> runCatching { JSONObject(line).optString("message") }.getOrNull() }
        ?.takeIf { it.isNotBlank() }
    return bridgeMessage ?: result.stderr.trim().ifBlank { "重启请求失败，请长按电源键手动重启。" }
}
