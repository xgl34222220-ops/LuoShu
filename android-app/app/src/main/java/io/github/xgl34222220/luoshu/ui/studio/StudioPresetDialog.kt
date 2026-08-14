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
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.Edit
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Save
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarBorder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch

@Composable
internal fun StudioPresetDialog(
    style: UiStyle,
    state: FontStudioUiState,
    actions: FontStudioActions,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val store = remember(context.applicationContext) { StudioPresetStore(context.applicationContext) }
    var presets by remember { mutableStateOf(emptyList<StoredStudioPreset>()) }
    var name by remember { mutableStateOf(defaultPresetName()) }
    var loading by remember { mutableStateOf(true) }
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }
    var renaming by remember { mutableStateOf<StoredStudioPreset?>(null) }
    var renameText by remember { mutableStateOf("") }

    suspend fun reload() {
        presets = store.list()
        loading = false
    }

    LaunchedEffect(Unit) {
        runCatching { reload() }.onFailure {
            loading = false
            errorMessage = it.message ?: "方案库读取失败"
        }
    }

    fun saveCurrent() {
        if (busy || state.slots.any { it.font == null }) return
        scope.launch {
            busy = true
            status = ""
            errorMessage = ""
            runCatching {
                store.save(name, encodeStudioProfile(state))
                reload()
            }.onSuccess {
                status = "已保存：${sanitizePresetName(name)}"
                name = defaultPresetName()
            }.onFailure {
                errorMessage = it.message ?: "方案保存失败"
            }
            busy = false
        }
    }

    fun applyPreset(item: StoredStudioPreset) {
        if (busy) return
        scope.launch {
            busy = true
            status = ""
            errorMessage = ""
            val parsed = parseStudioProfile(item.profileRaw, state.fonts)
            if (parsed.valid && parsed.profile != null) {
                applyStudioProfile(parsed.profile, actions)
                runCatching { store.touch(item.id); reload() }
                status = buildString {
                    append("已载入：${item.name}")
                    if (parsed.warnings.isNotEmpty()) append("\n${parsed.warnings.joinToString("\n")}")
                }
            } else {
                errorMessage = parsed.errors.joinToString("\n").ifBlank { "方案内容无效" }
            }
            busy = false
        }
    }

    fun deletePreset(item: StoredStudioPreset) {
        if (busy) return
        scope.launch {
            busy = true
            runCatching { store.delete(item.id); reload() }
                .onSuccess { status = "已删除：${item.name}"; errorMessage = "" }
                .onFailure { errorMessage = it.message ?: "删除失败" }
            busy = false
        }
    }

    fun toggleFavorite(item: StoredStudioPreset) {
        if (busy) return
        scope.launch {
            runCatching { store.toggleFavorite(item.id); reload() }
                .onFailure { errorMessage = it.message ?: "收藏状态更新失败" }
        }
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = {
            if (busy) CircularProgressIndicator(Modifier.size(25.dp), strokeWidth = 2.dp)
            else Icon(Icons.Rounded.Save, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        },
        title = { Text("本地字体方案库", fontWeight = FontWeight.Black) },
        text = {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "保存中文、英文、数字 Family、字重与变量轴。收藏方案置顶，最近使用方案自动排序，方便快速回到上一套搭配。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                    lineHeight = 15.sp,
                )
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.take(48) },
                    label = { Text("方案名称") },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(
                    onClick = ::saveCurrent,
                    enabled = !busy && state.slots.all { it.font != null },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Icon(Icons.Rounded.Save, contentDescription = null, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("保存当前组合")
                }

                when {
                    loading -> {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
                            CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                        }
                    }
                    presets.isEmpty() -> {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(18.dp),
                            color = MaterialTheme.colorScheme.surfaceContainer,
                        ) {
                            Text(
                                "还没有本地方案。保存后可在这里一键载入。",
                                modifier = Modifier.padding(12.dp),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 10.sp,
                            )
                        }
                    }
                    else -> {
                        Text("我的方案 · ${presets.size}", fontSize = 11.sp, fontWeight = FontWeight.Black)
                        LazyColumn(
                            modifier = Modifier.fillMaxWidth().heightIn(max = 330.dp),
                            verticalArrangement = Arrangement.spacedBy(7.dp),
                        ) {
                            items(presets, key = { it.id }) { preset ->
                                PresetRow(
                                    preset = preset,
                                    enabled = !busy,
                                    onApply = { applyPreset(preset) },
                                    onFavorite = { toggleFavorite(preset) },
                                    onRename = {
                                        renaming = preset
                                        renameText = preset.name
                                    },
                                    onDelete = { deletePreset(preset) },
                                )
                            }
                        }
                    }
                }

                if (status.isNotBlank()) {
                    Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                        Text(status, modifier = Modifier.fillMaxWidth().padding(10.dp), fontSize = 10.sp)
                    }
                }
                if (errorMessage.isNotBlank()) {
                    Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.errorContainer) {
                        Text(
                            errorMessage,
                            modifier = Modifier.fillMaxWidth().padding(10.dp),
                            color = MaterialTheme.colorScheme.onErrorContainer,
                            fontSize = 10.sp,
                        )
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss, enabled = !busy) { Text("完成") } },
    )

    renaming?.let { preset ->
        AlertDialog(
            onDismissRequest = { renaming = null },
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 32.dp else 26.dp),
            icon = { Icon(Icons.Rounded.Edit, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
            title = { Text("重命名方案", fontWeight = FontWeight.Black) },
            text = {
                OutlinedTextField(
                    value = renameText,
                    onValueChange = { renameText = it.take(48) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            dismissButton = { TextButton(onClick = { renaming = null }) { Text("取消") } },
            confirmButton = {
                TextButton(
                    onClick = {
                        val target = preset
                        val newName = renameText
                        renaming = null
                        scope.launch {
                            busy = true
                            runCatching { store.rename(target.id, newName); reload() }
                                .onSuccess { status = "已重命名为：${sanitizePresetName(newName)}"; errorMessage = "" }
                                .onFailure { errorMessage = it.message ?: "重命名失败" }
                            busy = false
                        }
                    },
                ) { Text("保存", fontWeight = FontWeight.Bold) }
            },
        )
    }
}

@Composable
private fun PresetRow(
    preset: StoredStudioPreset,
    enabled: Boolean,
    onApply: () -> Unit,
    onFavorite: () -> Unit,
    onRename: () -> Unit,
    onDelete: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 11.dp, top = 9.dp, end = 6.dp, bottom = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onFavorite, enabled = enabled, modifier = Modifier.size(36.dp)) {
                Icon(
                    if (preset.favorite) Icons.Rounded.Star else Icons.Rounded.StarBorder,
                    contentDescription = if (preset.favorite) "取消收藏" else "收藏方案",
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(19.dp),
                )
            }
            Spacer(Modifier.width(5.dp))
            Column(Modifier.weight(1f)) {
                Text(preset.name, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = 12.sp, fontWeight = FontWeight.Black)
                Text(
                    when {
                        preset.lastUsedAt > 0L -> "最近使用 ${formatPresetTime(preset.lastUsedAt)}"
                        else -> "保存于 ${formatPresetTime(preset.createdAt)}"
                    },
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 9.sp,
                )
            }
            IconButton(onClick = onRename, enabled = enabled, modifier = Modifier.size(34.dp)) {
                Icon(Icons.Rounded.Edit, contentDescription = "重命名", modifier = Modifier.size(17.dp))
            }
            IconButton(onClick = onDelete, enabled = enabled, modifier = Modifier.size(34.dp)) {
                Icon(Icons.Rounded.Delete, contentDescription = "删除", tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(17.dp))
            }
            OutlinedButton(onClick = onApply, enabled = enabled, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 9.dp, vertical = 5.dp)) {
                Icon(Icons.Rounded.PlayArrow, contentDescription = null, modifier = Modifier.size(16.dp))
                Text("载入", fontSize = 9.sp)
            }
        }
    }
}

private fun defaultPresetName(): String = "方案 " + SimpleDateFormat("MM-dd HH:mm", Locale.CHINA).format(Date())
private fun formatPresetTime(time: Long): String = if (time <= 0L) "—" else SimpleDateFormat("MM-dd HH:mm", Locale.CHINA).format(Date(time))
