package io.github.xgl34222220.luoshu.ui.home

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import org.json.JSONArray
import org.json.JSONObject

@Immutable
internal data class DeviceAcceptanceCheck(
    val id: String,
    val title: String,
    val detail: String,
    val passed: Boolean,
    val automatic: Boolean,
)

private val manualAcceptanceChecks = listOf(
    DeviceAcceptanceCheck("system-ui", "系统界面", "检查设置、状态栏、通知、锁屏和桌面是否无方框、截断或错位", false, false),
    DeviceAcceptanceCheck("input", "输入与编辑", "检查输入法候选、光标、选择菜单、中英文混排和密码框", false, false),
    DeviceAcceptanceCheck("apps", "常用应用", "检查浏览器、社交、阅读和 Google 应用中的字体回退", false, false),
    DeviceAcceptanceCheck("numbers", "数字场景", "检查时间、电量、金额、验证码、表格和等宽数字是否清晰", false, false),
)

internal fun deviceAcceptanceAutoChecks(
    state: HomeUiState,
    trust: DeviceTrustState,
): List<DeviceAcceptanceCheck> = listOf(
    DeviceAcceptanceCheck(
        id = "root",
        title = "Root 与模块连接",
        detail = if (state.rootGranted && state.moduleInstalled) "Root 已授权，洛书模块已连接" else "需要 Root 授权并安装匹配模块",
        passed = state.rootGranted && state.moduleInstalled,
        automatic = true,
    ),
    DeviceAcceptanceCheck(
        id = "task",
        title = "字体任务结束",
        detail = if (state.taskRunning) state.taskMessage else "当前没有执行中的字体任务",
        passed = !state.taskRunning,
        automatic = true,
    ),
    DeviceAcceptanceCheck(
        id = "reboot",
        title = "完整重启已完成",
        detail = if (state.rebootRequired) "当前字体仍等待完整重启" else "没有待重启的字体变更",
        passed = !state.rebootRequired,
        automatic = true,
    ),
    DeviceAcceptanceCheck(
        id = "inventory",
        title = "原厂字体清单",
        detail = if (trust.inventory == "available") "已建立设备原厂字体清单" else "原厂字体清单缺失或尚未生成",
        passed = trust.inventory == "available",
        automatic = true,
    ),
    DeviceAcceptanceCheck(
        id = "alignment",
        title = "开机加载证据",
        detail = if (trust.alignment == "verified" && trust.mode == "aligned") {
            "开机加载验证通过，当前为设备对齐模式"
        } else {
            "等待开机加载验证；兼容模式不能视为真机验收完成"
        },
        passed = trust.alignment == "verified" && trust.mode == "aligned",
        automatic = true,
    ),
    DeviceAcceptanceCheck(
        id = "cache",
        title = "后台对齐缓存",
        detail = if (trust.cachePending) "仍有对齐缓存等待生成" else "没有待处理的对齐缓存",
        passed = !trust.cachePending,
        automatic = true,
    ),
)

internal class DeviceAcceptanceStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "device-acceptance-v1",
        Context.MODE_PRIVATE,
    )

    fun load(key: String): Set<String> = runCatching {
        val root = JSONObject(preferences.getString(storageKey(key), "{}") ?: "{}")
        val values = root.optJSONArray("completed") ?: JSONArray()
        buildSet {
            for (index in 0 until values.length()) {
                values.optString(index).takeIf { id -> manualAcceptanceChecks.any { it.id == id } }?.let(::add)
            }
        }
    }.getOrDefault(emptySet())

    fun save(key: String, completed: Set<String>) {
        val allowed = completed.filter { id -> manualAcceptanceChecks.any { it.id == id } }.sorted()
        preferences.edit()
            .putString(storageKey(key), JSONObject().put("completed", JSONArray(allowed)).toString())
            .apply()
    }

    private fun storageKey(key: String): String = "acceptance-${key.hashCode()}"
}

@Composable
internal fun DeviceAcceptanceGuideDialog(
    style: UiStyle,
    state: HomeUiState,
    trust: DeviceTrustState,
    onRefresh: () -> Unit,
    onReboot: () -> Unit,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val store = remember(context) { DeviceAcceptanceStore(context) }
    val recordKey = "${state.version}|${state.currentFont}"
    var completedManual by remember(recordKey) { mutableStateOf(store.load(recordKey)) }
    var copied by remember { mutableStateOf(false) }
    val automatic = deviceAcceptanceAutoChecks(state, trust)
    val manual = manualAcceptanceChecks.map { it.copy(passed = it.id in completedManual) }
    val allChecks = automatic + manual
    val passedCount = allChecks.count { it.passed }
    val complete = passedCount == allChecks.size

    fun toggleManual(id: String) {
        completedManual = if (id in completedManual) completedManual - id else completedManual + id
        store.save(recordKey, completedManual)
    }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 800.dp),
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 36.dp else 30.dp),
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
            shadowElevation = 14.dp,
        ) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 15.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(48.dp),
                        shape = RoundedCornerShape(17.dp),
                        color = if (complete) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.secondaryContainer,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                if (complete) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                                contentDescription = null,
                                tint = if (complete) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.secondary,
                            )
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("真机验收向导", fontSize = 20.sp, fontWeight = FontWeight.Black)
                        Text(
                            if (complete) "自动证据与人工场景均已确认" else "已完成 $passedCount/${allChecks.size} 项",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                        )
                    }
                    IconButton(onClick = onDismiss) { Icon(Icons.Rounded.Close, contentDescription = "关闭") }
                }

                Spacer(Modifier.size(12.dp))
                LinearProgressIndicator(
                    progress = { passedCount.toFloat() / allChecks.size.coerceAtLeast(1) },
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.size(10.dp))

                LazyColumn(
                    modifier = Modifier.weight(1f, fill = false),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    item {
                        Text("自动验证", fontSize = 14.sp, fontWeight = FontWeight.Black)
                    }
                    items(automatic, key = { it.id }) { check ->
                        DeviceAcceptanceRow(check = check)
                    }
                    item {
                        Text(
                            "人工场景",
                            modifier = Modifier.padding(top = 6.dp),
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                    items(manual, key = { it.id }) { check ->
                        DeviceAcceptanceRow(check = check, onToggle = { toggleManual(check.id) })
                    }
                }

                Spacer(Modifier.size(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onRefresh, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Rounded.Refresh, contentDescription = null, modifier = Modifier.size(17.dp))
                        Spacer(Modifier.size(5.dp))
                        Text("重新检测")
                    }
                    OutlinedButton(
                        onClick = {
                            clipboard.setText(AnnotatedString(deviceAcceptanceSummary(state, trust, allChecks)))
                            copied = true
                        },
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.Rounded.ContentCopy, contentDescription = null, modifier = Modifier.size(17.dp))
                        Spacer(Modifier.size(5.dp))
                        Text(if (copied) "已复制" else "复制摘要")
                    }
                }
                if (state.rebootRequired) {
                    TextButton(onClick = onReboot, modifier = Modifier.align(Alignment.CenterHorizontally)) {
                        Text("立即完整重启", color = MaterialTheme.colorScheme.error, fontWeight = FontWeight.Black)
                    }
                } else {
                    TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) {
                        Text("完成", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun DeviceAcceptanceRow(
    check: DeviceAcceptanceCheck,
    onToggle: (() -> Unit)? = null,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = if (check.passed) {
            MaterialTheme.colorScheme.primaryContainer.copy(alpha = .48f)
        } else {
            MaterialTheme.colorScheme.surfaceContainerLow
        },
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 11.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (check.automatic) {
                Icon(
                    if (check.passed) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                    contentDescription = null,
                    tint = if (check.passed) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(22.dp),
                )
            } else {
                Checkbox(checked = check.passed, onCheckedChange = { onToggle?.invoke() })
            }
            Spacer(Modifier.width(9.dp))
            Column(Modifier.weight(1f)) {
                Text(check.title, fontSize = 12.sp, fontWeight = FontWeight.Black)
                Text(check.detail, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, lineHeight = 13.sp)
            }
        }
    }
}

private fun deviceAcceptanceSummary(
    state: HomeUiState,
    trust: DeviceTrustState,
    checks: List<DeviceAcceptanceCheck>,
): String = buildString {
    appendLine("洛书真机验收摘要")
    appendLine("版本：${state.version}")
    appendLine("当前字体：${state.currentFont}")
    appendLine("可信级别：${trust.level.name.lowercase()}")
    appendLine("完成度：${checks.count { it.passed }}/${checks.size}")
    appendLine()
    checks.forEach { check -> appendLine("[${if (check.passed) "通过" else "待确认"}] ${check.title}：${check.detail}") }
    appendLine()
    append("摘要不包含设备指纹、序列号、型号或字体文件路径。")
}
