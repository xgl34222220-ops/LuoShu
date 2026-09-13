package io.github.xgl34222220.luoshu.ui.settings

import android.os.Process
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import io.github.xgl34222220.luoshu.RootShell
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

internal data class GoogleFontCompatibilityState(
    val loading: Boolean = true,
    val busy: Boolean = false,
    val state: String = "unknown",
    val title: String = "正在读取组件状态…",
    val message: String = "只检测，不会自动开启。",
    val user: Int? = null,
    val canEnable: Boolean = false,
    val canRestore: Boolean = false,
    val managed: Boolean = false,
    val componentDisabled: Boolean = false,
    val resultMessage: String = "",
    val error: String = "",
)

/** Permission buttons come from a verified snapshot, never saved UI preferences. */
internal fun parseGoogleFontCompatibility(raw: String, expectedUser: Int): GoogleFontCompatibilityState {
    val json = JSONObject(raw.trim())
    require(json.optString("status") == "diagnostic") { "未收到有效的组件状态，请重新检测。" }
    require(json.getInt("user") == expectedUser) { "Android 用户发生变化，请重新进入本页。" }
    val state = json.getString("state")
    require(state in setOf("enabled", "off", "external", "conflict", "unavailable", "changed")) {
        "组件状态无法识别；没有修改设置。"
    }
    val managed = json.optBoolean("managed", false)
    val disabled = json.optBoolean("componentDisabled", false)
    return GoogleFontCompatibilityState(
        loading = false,
        state = state,
        title = json.getString("title"),
        message = json.getString("message"),
        user = expectedUser,
        managed = managed,
        componentDisabled = disabled,
        canEnable = state == "off" && !managed && !disabled && json.optBoolean("canEnable", false),
        canRestore = state in setOf("enabled", "changed", "unavailable") && managed && json.optBoolean("canRestore", false),
    )
}

internal fun googleFontActionMessage(action: String, status: String): String = when {
    action == "enable" && status == "component-disabled" -> "已开启兼容设置。请完整重启，再检查谷歌商店的英文和数字。"
    action == "enable" && status == "externally-disabled" -> "组件已被其他方式停用，洛书没有接管或修改它。"
    action == "restore" && status == "restored" -> "已恢复开启前的组件设置。请完整重启手机。"
    action == "restore" && status == "unchanged" -> "没有洛书的修改记录；未擅自启用组件。"
    else -> throw IllegalArgumentException("操作结果未核验成功，请重新检测当前状态。")
}

internal fun googleFontCommand(action: String, user: Int): String {
    require(action in setOf("status", "enable", "restore"))
    require(user in 0..21474)
    val path = "/data/adb/modules/LuoShu/common/google_font_fallback.sh"
    return "if [ -f ${RootShell.quote(path)} ]; then /system/bin/sh ${RootShell.quote(path)} " +
        "$action --user $user --json; else printf '%s\\n' " +
        RootShell.quote("""{"status":"error","message":"当前模块尚未内置此功能，请安装配套模块并完整重启。"}""") +
        "; exit 1; fi"
}

internal class GoogleFontCompatibilityModel : ViewModel() {
    // Bind actions to the App's Android user, never assume owner/user 0.
    private val appUser = Process.myUid() / 100000
    var ui by mutableStateOf(GoogleFontCompatibilityState())
        private set
    private var running = false

    fun refresh() = request("status")
    fun enable() { if (ui.canEnable) request("enable") }
    fun restore() { if (ui.canRestore) request("restore") }

    private fun request(action: String) {
        if (running) return
        running = true
        ui = ui.copy(loading = action == "status", busy = action != "status", error = "")
        viewModelScope.launch {
            try {
                val result = RootShell.exec(googleFontCommand(action, appUser), timeoutMs = 100_000L)
                val json = runCatching { JSONObject(result.stdout.trim()) }.getOrNull()
                if (result.code != 0 || json?.optString("status") == "error") {
                    val message = json?.optString("message")?.takeIf { it.isNotBlank() }
                        ?: "无法完成操作。请确认已授予洛书 Root 权限、配套模块已启用，并在重启后重新检测。"
                    ui = ui.copy(loading = false, busy = false, title = "暂时无法读取状态", canEnable = false, canRestore = false, error = message)
                } else if (action == "status") {
                    val last = ui.resultMessage
                    ui = parseGoogleFontCompatibility(result.stdout, appUser).copy(resultMessage = last)
                } else {
                    val message = googleFontActionMessage(action, json?.optString("status").orEmpty())
                    val current = json?.optJSONObject("current")
                    ui = if (current != null) {
                        parseGoogleFontCompatibility(current.toString(), appUser).copy(resultMessage = message)
                    } else {
                        GoogleFontCompatibilityState(loading = false, title = "请重新检测当前状态", message = message,
                            resultMessage = message, error = "后续状态读取未完成，请点击重新检测。")
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                ui = ui.copy(loading = false, busy = false, title = "暂时无法读取状态", canEnable = false, canRestore = false,
                    error = "状态读取或结果核验失败，请重新检测。")
            } finally {
                running = false
                ui = ui.copy(loading = false, busy = false)
            }
        }
    }
}
