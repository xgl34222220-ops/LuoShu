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
    SYSTEM,
    VERIFIED,
    COMPATIBILITY,
    PENDING,
    ISSUE,
}

private val pendingTrustReasons = setOf(
    "awaiting-full-reboot",
    "boot-not-completed",
    "background-task-still-running",
    "stale-verification",
    "stale-self-mount",
    "awaiting-boot-transaction",
    "stale-boot-transaction",
    "dynamic-config-unconfirmed",
)

private val failedTrustReasons = setOf(
    "self-mount-not-visible",
    "self-mount-failed",
    "self-mount-invalid-backend",
    "self-mount-manifest-missing",
    "aligned-manifest-missing",
    "dynamic-config-overridden",
    "dynamic-config-mount-failed",
    "verifier-output-missing",
    "verification-retry-exhausted",
)

internal data class DeviceTrustState(
    val loading: Boolean = true,
    val activeFont: String = "unknown",
    val inventory: String = "unknown",
    val engine: String = "unknown",
    val template: String = "unknown",
    val alignment: String = "unknown",
    val mode: String = "unknown",
    val reason: String = "",
    val mountState: String = "unknown",
    val cachePending: Boolean = false,
    val error: String = "",
) {
    val level: DeviceTrustLevel
        get() = when {
            error.isNotBlank() -> DeviceTrustLevel.ISSUE
            activeFont in setOf("", "default") || alignment == "not-applicable" -> DeviceTrustLevel.SYSTEM
            mountState == "failed" -> DeviceTrustLevel.ISSUE
            alignment == "failed" || reason in failedTrustReasons -> DeviceTrustLevel.ISSUE
            alignment == "verified" && mode in setOf("aligned", "mount-verified", "mount-confirmed") -> DeviceTrustLevel.VERIFIED
            alignment == "pending" || reason in pendingTrustReasons -> DeviceTrustLevel.PENDING
            alignment == "compatibility" || mode == "compatibility" -> DeviceTrustLevel.COMPATIBILITY
            engine == "installed" -> DeviceTrustLevel.PENDING
            inventory == "available" -> DeviceTrustLevel.COMPATIBILITY
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
        active="${'$'}(head -n1 "${'$'}CFG/active_font.conf" 2>/dev/null | tr -d '\r\n')"
        [ -n "${'$'}active" ] || active=default
        inventory=missing
        [ -s "${'$'}CFG/device_font_inventory.json" ] && inventory=available
        engine="${'$'}(read_value "${'$'}CFG/device-font-engine.conf" state)"
        template="${'$'}(read_value "${'$'}CFG/device-font-template.state" state)"
        alignment="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" state)"
        mode="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" mode)"
        reason="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" reason)"
        verifiedActive="${'$'}(read_value "${'$'}CFG/device-font-load-verification.conf" activeFont)"
        mountState="${'$'}(read_value "${'$'}CFG/self-mount.conf" state)"
        if [ "${'$'}active" != default ]; then
            if [ "${'$'}mountState" = failed ]; then
                [ "${'$'}alignment" = failed ] || reason=self-mount-failed
                alignment=failed
                mode=compatibility
            elif [ -n "${'$'}verifiedActive" ] && [ "${'$'}verifiedActive" != "${'$'}active" ]; then
                alignment=pending
                mode=unknown
                reason=stale-verification
            fi
        fi
        cachePending=no
        [ -s "${'$'}CFG/device-font-cache-pending.conf" ] && cachePending=yes
        printf 'activeFont=%s\ninventory=%s\nengine=%s\ntemplate=%s\nalignment=%s\nmode=%s\nreason=%s\nmountState=%s\ncachePending=%s\n' \
            "${'$'}active" "${'$'}inventory" "${'$'}{engine:-missing}" "${'$'}{template:-missing}" \
            "${'$'}{alignment:-pending}" "${'$'}{mode:-compatibility}" "${'$'}reason" \
            "${'$'}{mountState:-missing}" "${'$'}cachePending"
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
        activeFont = values["activeFont"].orEmpty().ifBlank { "default" },
        inventory = values["inventory"].orEmpty().ifBlank { "unknown" },
        engine = values["engine"].orEmpty().ifBlank { "unknown" },
        template = values["template"].orEmpty().ifBlank { "unknown" },
        alignment = values["alignment"].orEmpty().ifBlank { "unknown" },
        mode = values["mode"].orEmpty().ifBlank { "unknown" },
        reason = values["reason"].orEmpty(),
        mountState = values["mountState"].orEmpty().ifBlank { "unknown" },
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
    onOpenAcceptance: () -> Unit = {},
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
                DeviceTrustRow("当前字体", friendlyActiveFont(state.activeFont))
                DeviceTrustRow("原厂字体清单", friendlyTrustValue(state.inventory))
                DeviceTrustRow("设备字体引擎", friendlyTrustValue(state.engine))
                DeviceTrustRow("原厂模板", friendlyTrustValue(state.template))
                DeviceTrustRow("开机加载验证", friendlyTrustValue(state.alignment))
                DeviceTrustRow("加载模式", friendlyTrustValue(state.mode))
                DeviceTrustRow("自挂载事务", friendlyTrustValue(state.mountState))
                if (state.reason.isNotBlank()) {
                    DeviceTrustRow("验证说明", friendlyTrustReason(state.reason))
                }
                DeviceTrustRow("后台对齐缓存", if (state.cachePending) "等待生成" else "无待处理任务")
                if (state.error.isNotBlank()) {
                    Spacer(Modifier.size(8.dp))
                    Text(state.error, color = MaterialTheme.colorScheme.error, fontSize = 11.sp)
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("完成") } },
        dismissButton = {
            TextButton(
                onClick = {
                    onDismiss()
                    onOpenAcceptance()
                },
            ) { Text("真机验收", fontWeight = FontWeight.Black) }
        },
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
        state.level == DeviceTrustLevel.SYSTEM -> DeviceTrustPresentation(
            "当前为系统字体",
            "没有启用洛书字体，无需进行加载验证",
            Icons.Rounded.CheckCircle,
            scheme.primary,
        )
        state.level == DeviceTrustLevel.VERIFIED && state.mode == "mount-verified" -> DeviceTrustPresentation(
            "本次启动字体已验证",
            "PID 1 可见字体、配置与洛书负载一致",
            Icons.Rounded.CheckCircle,
            scheme.primary,
        )
        state.level == DeviceTrustLevel.VERIFIED && state.mode == "mount-confirmed" -> DeviceTrustPresentation(
            "本次启动挂载已确认",
            "字体事务已完成；系统字体服务暴露的目录布局与负载不同",
            Icons.Rounded.CheckCircle,
            scheme.primary,
        )
        state.level == DeviceTrustLevel.VERIFIED -> DeviceTrustPresentation(
            "本次启动字体已验证",
            "原厂模板、字体事务与本次启动证据一致",
            Icons.Rounded.CheckCircle,
            scheme.primary,
        )
        state.level == DeviceTrustLevel.COMPATIBILITY -> DeviceTrustPresentation(
            "字体效果尚未确认",
            "已生成兼容映射，但没有系统实际加载证据",
            Icons.Rounded.Info,
            scheme.tertiary,
        )
        state.level == DeviceTrustLevel.ISSUE -> DeviceTrustPresentation(
            "字体应用失败",
            friendlyTrustReason(state.reason).ifBlank { "加载验证失败，请根据说明修复后重新应用" },
            Icons.Rounded.Warning,
            scheme.error,
        )
        else -> DeviceTrustPresentation(
            if (state.reason == "awaiting-full-reboot") "字体已准备，等待重启" else "等待本次启动验证",
            friendlyTrustReason(state.reason).ifBlank { "开机验证尚未完成，可查看验证说明" },
            Icons.Rounded.Info,
            scheme.secondary,
        )
    }
}

private fun friendlyActiveFont(value: String): String = when (value) {
    "", "default" -> "系统默认"
    "mix" -> "组合字体"
    else -> "自定义字体"
}

private fun friendlyTrustReason(value: String): String = when (value) {
    "default-font" -> "系统字体无需验证"
    "awaiting-full-reboot" -> "等待完整重启"
    "boot-not-completed" -> "Android 尚未完成启动"
    "background-task-still-running" -> "后台字体任务尚未结束"
    "aligned-payload-not-active" -> "当前字体使用兼容映射"
    "aligned-manifest-missing" -> "设备专属负载清单缺失"
    "verifier-output-missing" -> "验证器没有返回结果"
    "verification-retry-exhausted" -> "多次自动验证仍未完成"
    "self-mount-not-visible" -> "开机挂载未完整生效，当前使用系统默认字体"
    "self-mount-failed" -> "本次启动原子挂载失败，字体与配置已完整回滚"
    "self-mount-invalid-backend" -> "挂载后端不受支持，洛书没有提交字体负载"
    "self-mount-manifest-missing" -> "本次启动挂载清单缺失，字体与配置没有生效"
    "stale-self-mount" -> "挂载记录属于上一次启动，等待本次启动重新确认"
    "awaiting-boot-transaction" -> "等待本次启动的字体事务完成确认"
    "stale-boot-transaction" -> "字体事务记录属于上一次启动，需要重新应用字体"
    "dynamic-config-unconfirmed" -> "系统动态字体配置尚未确认"
    "dynamic-config-overridden" -> "系统动态字体配置覆盖了洛书负载，当前使用系统字体"
    "dynamic-config-mount-failed" -> "系统动态字体配置挂载失败，已完整回滚"
    "stale-verification" -> "验证记录与当前选择的字体不一致"
    "self-mount-not-confirmed" -> "本次启动的自挂载事务尚未确认"
    "current-boot-mount-confirmed" -> "本次启动的字体、配置与挂载事务均已确认"
    "dynamic-config-changed" -> "系统在启动后改写了动态字体配置"
    "verified-by-visible-mounts" -> "系统可见字体文件与洛书负载一致"
    "mount-transaction-active" -> "本次启动的字体挂载事务已确认"
    "mount-active-visible-layout-differs" -> "字体挂载已确认，系统可见目录布局与模块负载不同"
    else -> value
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
    "unverified" -> "证据不足"
    "not-applicable" -> "不适用"
    "aligned" -> "设备对齐"
    "mount-verified" -> "挂载证据"
    "mount-confirmed" -> "事务确认"
    "compatibility" -> "兼容映射"
    "mounted" -> "完整挂载"
    "idle" -> "未启用"
    "unknown", "" -> "未知"
    else -> value
}
