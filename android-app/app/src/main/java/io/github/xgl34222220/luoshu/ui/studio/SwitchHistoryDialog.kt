package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material.icons.rounded.History
import androidx.compose.material.icons.rounded.Restore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch
import org.json.JSONObject

private const val SWITCH_HISTORY_TOOL = "/data/adb/modules/LuoShu/system/bin/luoshu-history"

internal data class SwitchHistoryEntry(
    val id: String,
    val type: String,
    val time: Long,
    val font: String = "",
    val cjk: String = "",
    val latin: String = "",
    val digit: String = "",
    val cjkAxes: String = "",
    val latinAxes: String = "",
    val digitAxes: String = "",
) {
    val title: String get() = if (type == "direct") font.ifBlank { "直接字体" } else "组合字体"
    val description: String get() = if (type == "direct") {
        "直接应用 · ${formatSwitchTime(time)}"
    } else {
        listOf(cjk, latin, digit).filter { it.isNotBlank() }.joinToString(" · ") + " · ${formatSwitchTime(time)}"
    }
}

internal suspend fun recordSuccessfulMixHistory() {
    RootShell.exec("sh ${RootShell.quote(SWITCH_HISTORY_TOOL)} record-mix", timeoutMs = 12_000L)
}

internal fun parseSwitchHistory(raw: String): List<SwitchHistoryEntry> {
    val root = JSONObject(raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }?.trim().orEmpty())
    if (root.optString("status") != "ok") return emptyList()
    val array = root.optJSONArray("entries") ?: return emptyList()
    return buildList {
        for (index in 0 until array.length()) {
            val item = array.optJSONObject(index) ?: continue
            val id = item.optString("id").trim()
            val type = item.optString("type").trim()
            if (id.isBlank() || type !in setOf("direct", "mix")) continue
            add(
                SwitchHistoryEntry(
                    id = id,
                    type = type,
                    time = item.optLong("time", 0L).coerceAtLeast(0L),
                    font = item.optString("font").trim(),
                    cjk = item.optString("cjk").trim(),
                    latin = item.optString("latin").trim(),
                    digit = item.optString("digit").trim(),
                    cjkAxes = item.optString("cjkAxes").trim(),
                    latinAxes = item.optString("latinAxes").trim(),
                    digitAxes = item.optString("digitAxes").trim(),
                ),
            )
        }
    }
}

@Composable
internal fun SwitchHistoryDialog(
    style: UiStyle,
    onDismiss: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    var entries by remember { mutableStateOf(emptyList<SwitchHistoryEntry>()) }
    var loading by remember { mutableStateOf(true) }
    var busyId by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }

    fun refresh() {
        scope.launch {
            loading = true
            val result = RootShell.exec("sh ${RootShell.quote(SWITCH_HISTORY_TOOL)} list", timeoutMs = 12_000L)
            entries = if (result.code == 0) runCatching { parseSwitchHistory(result.stdout) }.getOrDefault(emptyList()) else emptyList()
            error = if (result.code == 0) "" else result.stderr.ifBlank { "无法读取切换历史" }
            loading = false
        }
    }
    LaunchedEffect(Unit) { refresh() }

    AlertDialog(
        onDismissRequest = { if (busyId.isBlank()) onDismiss() },
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = { Icon(Icons.Rounded.History, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
        title = { Text("最近成功切换", fontWeight = FontWeight.Black) },
        text = {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "只记录真正完成的字体事务，最多保留 10 次。恢复仍会重新走洛书的校验、事务与重启保护。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                )
                when {
                    loading -> Row(Modifier.fillMaxWidth().padding(vertical = 24.dp), horizontalArrangement = Arrangement.Center) {
                        CircularProgressIndicator(Modifier.size(26.dp), strokeWidth = 2.dp)
                    }
                    entries.isEmpty() -> Text("还没有成功切换记录", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    else -> LazyColumn(
                        modifier = Modifier.fillMaxWidth().heightIn(max = 410.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(entries, key = { it.id }) { entry ->
                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(18.dp),
                                color = MaterialTheme.colorScheme.surfaceContainer,
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Column(Modifier.weight(1f)) {
                                        Text(entry.title, fontSize = 12.sp, fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text(entry.description, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                    }
                                    Spacer(Modifier.width(8.dp))
                                    OutlinedButton(
                                        onClick = {
                                            scope.launch {
                                                busyId = entry.id; message = ""; error = ""
                                                val result = RootShell.exec(
                                                    "sh ${RootShell.quote(SWITCH_HISTORY_TOOL)} restore ${RootShell.quote(entry.id)}",
                                                    timeoutMs = 25_000L,
                                                )
                                                val root = runCatching {
                                                    JSONObject(result.stdout.lineSequence().firstOrNull { it.trimStart().startsWith("{") }?.trim().orEmpty())
                                                }.getOrNull()
                                                if (result.code == 0 && root?.optString("status") == "ok") {
                                                    message = "恢复任务已启动；完成后按提示完整重启"
                                                } else {
                                                    error = root?.optString("message").orEmpty().ifBlank { result.stderr.ifBlank { "无法启动恢复任务" } }
                                                }
                                                busyId = ""
                                            }
                                        },
                                        enabled = busyId.isBlank(),
                                    ) {
                                        if (busyId == entry.id) CircularProgressIndicator(Modifier.size(15.dp), strokeWidth = 2.dp)
                                        else Icon(Icons.Rounded.Restore, contentDescription = null, Modifier.size(16.dp))
                                        Spacer(Modifier.width(5.dp))
                                        Text("恢复", fontSize = 10.sp)
                                    }
                                }
                            }
                        }
                    }
                }
                if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.primary, fontSize = 10.sp)
                if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error, fontSize = 10.sp)
            }
        },
        confirmButton = { TextButton(onClick = onDismiss, enabled = busyId.isBlank()) { Text("完成") } },
        dismissButton = { if (!loading) TextButton(onClick = { refresh() }, enabled = busyId.isBlank()) { Text("刷新") } },
    )
}

private fun formatSwitchTime(epochSeconds: Long): String {
    if (epochSeconds <= 0L) return "时间未知"
    return SimpleDateFormat("MM-dd HH:mm", Locale.getDefault()).format(Date(epochSeconds * 1000L))
}
