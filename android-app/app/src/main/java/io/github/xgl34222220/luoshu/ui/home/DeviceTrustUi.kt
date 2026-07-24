package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

internal enum class DeviceTrustLevel {
    VERIFIED,
    READY,
    PENDING,
    ISSUE,
}

internal data class DeviceTrustState(
    val loading: Boolean = true,
    val inventory: String = "unknown",
    val engine: String = "unknown",
    val template: String = "unknown",
    val alignment: String = "unknown",
    val mode: String = "unknown",
    val cachePending: Boolean = false,
    val error: String = "",
) {
    val level: DeviceTrustLevel
        get() = when {
            error.isNotBlank() || alignment == "failed" -> DeviceTrustLevel.ISSUE
            alignment == "verified" && mode == "aligned" -> DeviceTrustLevel.VERIFIED
            inventory == "available" && engine !in setOf("missing", "failed", "unknown") -> DeviceTrustLevel.READY
            else -> DeviceTrustLevel.PENDING
        }
}

internal suspend fun loadDeviceTrustState(): DeviceTrustState {
    val command = """
        MOD=/data/adb/modules/LuoShu
        CFG="${'$'}MOD/config"
        read_value() {
            sed -n "s/^${'$'}2=//p" "${'$'}1" 2>/dev/null | head -n1 | tr -d '\r\n'
        }
        inventory=missing
        [ -s "${'$'}CFG/device_font_inventory.json" ] && inventory=available
        engine="${'$'}(read_value "${'$'}CFG/device-font-engine.conf" state)"
        template="${'$'}(read_value "${'$'}CFG/device-font-template.state" state)"
        alignment="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" state)"
        mode="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" mode)"
        cachePending=no
        [ -s "${'$'}CFG/device-font-cache-pending.conf" ] && cachePending=yes
        printf 'inventory=%s\nengine=%s\ntemplate=%s\nalignment=%s\nmode=%s\ncachePending=%s\n' \
            "${'$'}inventory" "${'$'}{engine:-missing}" "${'$'}{template:-missing}" \
            "${'$'}{alignment:-pending}" "${'$'}{mode:-compatibility}" "${'$'}cachePending"
    """.trimIndent()
    val result = RootShell.exec(command, timeoutMs = 12_000L)
    if (result.code != 0) {
        return DeviceTrustState(
            loading = false,
            error = result.stderr.ifBlank { "无法读取设备字体可信状态" },
        )
    }
    return parseDeviceTrustOutput(result.stdout)
}

internal fun parseDeviceTrustOutput(raw: String): DeviceTrustState {
    val values = raw.lineSequence().mapNotNull { line ->
        val split = line.indexOf('=')
        if (split <= 0) null else line.substring(0, split).trim() to line.substring(split + 1).trim()
    }.toMap()
    if (values.isEmpty()) {
        return DeviceTrustState(loading = false, error = "模块没有返回可信状态")
    }
    return DeviceTrustState(
        loading = false,
        inventory = values["inventory"].orEmpty().ifBlank { "unknown" },
        engine = values["engine"].orEmpty().ifBlank { "unknown" },
        template = values["template"].orEmpty().ifBlank { "unknown" },
        alignment = values["alignment"].orEmpty().ifBlank { "unknown" },
        mode = values["mode"].orEmpty().ifBlank { "unknown" },
        cachePending = values["cachePending"] == "yes",
    )
}

@Composable
internal fun DeviceTrustChip(
    style: UiStyle,
    state: DeviceTrustState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val presentation = deviceTrustPresentation(state)
    Surface(
        onClick = onClick,
        modifier = modifier,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 18.dp),
        color = presentation.color.copy(alpha = .12f),
        contentColor = presentation.color,
        shadowElevation = 5.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (state.loading) {
                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
            } else {
                Icon(presentation.icon, contentDescription = null, modifier = Modifier.size(19.dp))
            }
            Spacer(Modifier.width(8.dp))
            Column {
                Text(presentation.title, fontSize = 11.sp, fontWeight = FontWeight.Black)
                Text(presentation.subtitle, fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
internal fun DeviceTrustDialog(
    style: UiStyle,
    state: DeviceTrustState,
    onDismiss: () -> Unit,
) {
    val presentation = deviceTrustPresentation(state)
    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = { Icon(presentation.icon, contentDescription = null, tint = presentation.color) },
        title = { Text(presentation.title, fontWeight = FontWeight.Black) },
        text = {
            Column(Modifier.fillMaxWidth()) {
                Text(
                    presentation.subtitle,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
                Spacer(Modifier.size(12.dp))
                DeviceTrustRow("原厂字体清单", friendlyTrustValue(state.inventory))
                DeviceTrustRow("设备字体引擎", friendlyTrustValue(state.engine))
                DeviceTrustRow("原厂模板", friendlyTrustValue(state.template))
                DeviceTrustRow("开机加载验证", friendlyTrustValue(state.alignment))
                DeviceTrustRow("加载模式", friendlyTrustValue(state.mode))
                DeviceTrustRow("后台对齐缓存", if (state.cachePending) "等待生成" else "无待处理任务")
                if (state.error.isNotBlank()) {
                    Spacer(Modifier.size(8.dp))
                    Text(state.error, color = MaterialTheme.colorScheme.error, fontSize = 11.sp)
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("完成") } },
    )
}

@Composable
private fun DeviceTrustRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            label,
            modifier = Modifier.width(104.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(value, modifier = Modifier.weight(1f), fontSize = 12.sp, fontWeight = FontWeight.Medium)
    }
}

private data class DeviceTrustPresentation(
    val title: String,
    val subtitle: String,
    val icon: ImageVector,
    val color: Color,
)

@Composable
private fun deviceTrustPresentation(state: DeviceTrustState): DeviceTrustPresentation {
    val scheme = MaterialTheme.colorScheme
    return when {
        state.loading -> DeviceTrustPresentation("正在检查设备字体", "读取清单、模板与加载验证", Icons.Rounded.Info, scheme.primary)
        state.level == DeviceTrustLevel.VERIFIED -> DeviceTrustPresentation("设备字体已验证", "原厂模板与开机加载证据一致", Icons.Rounded.CheckCircle, scheme.primary)
        state.level == DeviceTrustLevel.READY -> DeviceTrustPresentation("设备字体引擎已就绪", "已发现原厂清单，等待完整加载验证", Icons.Rounded.Info, scheme.tertiary)
        state.level == DeviceTrustLevel.ISSUE -> DeviceTrustPresentation("设备字体需要检查", "加载验证失败或状态读取异常", Icons.Rounded.Warning, scheme.error)
        else -> DeviceTrustPresentation("设备字体尚未验证", "应用字体并完整重启后再次检查", Icons.Rounded.Info, scheme.secondary)
    }
}

private fun friendlyTrustValue(value: String): String = when (value) {
    "available" -> "有效"
    "missing" -> "缺失"
    "installed" -> "已安装"
    "ready" -> "已就绪"
    "trusted" -> "可信"
    "verified" -> "验证通过"
    "failed" -> "失败"
    "pending" -> "待验证"
    "aligned" -> "设备对齐"
    "compatibility" -> "兼容模式"
    "unknown", "" -> "未知"
    else -> value
}
