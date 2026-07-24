package io.github.xgl34222220.luoshu.ui.studio

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material.icons.rounded.FileUpload
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private const val STUDIO_PROFILE_SCHEMA = 1
private const val STUDIO_PROFILE_TYPE = "luoshu-studio-profile"
private const val STUDIO_PROFILE_MAX_CHARS = 262_144

@Immutable
internal data class StudioProfileSlot(
    val fontId: String,
    val fontName: String,
    val weight: Int,
    val axes: Map<String, Float>,
)

@Immutable
internal data class StudioProfile(
    val name: String,
    val slots: Map<MixSlot, StudioProfileSlot>,
)

@Immutable
internal data class StudioProfileParseResult(
    val profile: StudioProfile? = null,
    val errors: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
) {
    val valid: Boolean get() = profile != null && errors.isEmpty()
}

internal fun encodeStudioProfile(state: FontStudioUiState): String {
    val slots = JSONObject()
    state.slots.forEach { slot ->
        val font = slot.font ?: return@forEach
        slots.put(
            slot.slot.profileKey,
            JSONObject()
                .put("fontId", font.id)
                .put("fontName", font.name)
                .put("weight", slot.weight.coerceIn(1, 1000))
                .put(
                    "axes",
                    JSONObject().apply {
                        normalizedProfileAxes(slot.axes, slot.weight).toSortedMap().forEach { (tag, value) ->
                            put(tag, value.toDouble())
                        }
                    },
                ),
        )
    }
    return JSONObject()
        .put("schema", STUDIO_PROFILE_SCHEMA)
        .put("type", STUDIO_PROFILE_TYPE)
        .put("name", "洛书组合方案")
        .put("createdAt", System.currentTimeMillis())
        .put("slots", slots)
        .toString(2)
}

internal fun parseStudioProfile(
    raw: String,
    availableFonts: List<FontItem>,
): StudioProfileParseResult {
    val errors = mutableListOf<String>()
    val warnings = mutableListOf<String>()
    val root = runCatching { JSONObject(raw) }.getOrElse {
        return StudioProfileParseResult(errors = listOf("JSON 格式无效：${it.message ?: "无法解析"}"))
    }
    if (root.optInt("schema", -1) != STUDIO_PROFILE_SCHEMA) errors += "不支持的方案版本"
    if (root.optString("type") != STUDIO_PROFILE_TYPE) errors += "这不是洛书组合方案文件"
    val slotsObject = root.optJSONObject("slots")
    if (slotsObject == null) errors += "方案缺少 slots 配置"
    val fontMap = availableFonts.associateBy { it.id }
    val parsedSlots = linkedMapOf<MixSlot, StudioProfileSlot>()

    MixSlot.entries.forEach { slot ->
        val item = slotsObject?.optJSONObject(slot.profileKey)
        if (item == null) {
            errors += "缺少${slot.profileLabel}槽位"
            return@forEach
        }
        val fontId = item.optString("fontId").trim()
        val font = fontMap[fontId]
        when {
            fontId.isBlank() -> errors += "${slot.profileLabel}槽位没有字体 ID"
            font == null -> errors += "本机字体库缺少：${item.optString("fontName", fontId)}"
            !font.valid -> errors += "${font.name} 当前未通过字体验证"
        }
        if (font == null || !font.valid) return@forEach

        val weight = item.optInt("weight", 400).coerceIn(1, 1000)
        val axesObject = item.optJSONObject("axes") ?: JSONObject()
        val axes = linkedMapOf<String, Float>()
        val keys = axesObject.keys()
        while (keys.hasNext() && axes.size < 16) {
            val tag = keys.next().trim()
            val value = axesObject.optDouble(tag, Double.NaN).toFloat()
            if (tag.length == 4 && tag.all { it.code in 33..126 } && value.isFinite()) {
                axes[tag] = if (tag == "wght") value.coerceIn(1f, 1000f) else value
            } else {
                warnings += "已忽略 ${slot.profileLabel}槽位的无效设计轴：$tag"
            }
        }
        axes["wght"] = (axes["wght"] ?: weight.toFloat()).coerceIn(1f, 1000f)
        val savedName = item.optString("fontName").trim()
        if (savedName.isNotBlank() && savedName != font.name) warnings += "$savedName 在本机显示为 ${font.name}"
        parsedSlots[slot] = StudioProfileSlot(
            fontId = font.id,
            fontName = font.name,
            weight = axes.getValue("wght").toInt().coerceIn(1, 1000),
            axes = axes,
        )
    }

    if (errors.isNotEmpty() || parsedSlots.size != MixSlot.entries.size) {
        return StudioProfileParseResult(errors = errors.distinct(), warnings = warnings.distinct())
    }
    return StudioProfileParseResult(
        profile = StudioProfile(
            name = root.optString("name", "导入方案").ifBlank { "导入方案" },
            slots = parsedSlots,
        ),
        warnings = warnings.distinct(),
    )
}

internal fun applyStudioProfile(profile: StudioProfile, actions: FontStudioActions) {
    MixSlot.entries.forEach { slot ->
        val config = profile.slots[slot] ?: return@forEach
        actions.updateFont(slot, config.fontId)
        config.axes.forEach { (tag, value) -> actions.updateAxis(slot, tag, value) }
        actions.updateWeight(slot, config.weight)
    }
}

@Composable
internal fun StudioProfileTransferDialog(
    style: UiStyle,
    state: FontStudioUiState,
    actions: FontStudioActions,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pendingProfile by remember { mutableStateOf<StudioProfile?>(null) }
    var status by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json"),
    ) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    context.contentResolver.openOutputStream(uri, "wt")?.bufferedWriter()?.use { writer ->
                        writer.write(encodeStudioProfile(state))
                    } ?: throw IllegalStateException("无法打开目标文件")
                }
            }
            errorMessage = result.exceptionOrNull()?.message.orEmpty()
            status = if (result.isSuccess) "方案 JSON 已导出" else ""
        }
    }
    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val result = runCatching {
                withContext(Dispatchers.IO) { readProfileText(context.contentResolver, uri) }
            }.mapCatching { raw -> parseStudioProfile(raw, state.fonts) }
            val parsed = result.getOrNull()
            when {
                result.isFailure -> {
                    pendingProfile = null
                    status = ""
                    errorMessage = result.exceptionOrNull()?.message ?: "方案读取失败"
                }
                parsed == null || !parsed.valid -> {
                    pendingProfile = null
                    status = ""
                    errorMessage = parsed?.errors?.joinToString("\n") ?: "方案读取失败"
                }
                else -> {
                    pendingProfile = parsed.profile
                    errorMessage = ""
                    status = buildString {
                        append("已读取：${parsed.profile?.name}")
                        if (parsed.warnings.isNotEmpty()) append("\n${parsed.warnings.joinToString("\n")}")
                    }
                }
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        icon = { Icon(Icons.Rounded.Description, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
        title = { Text("组合方案 JSON", fontWeight = FontWeight.Black) },
        text = {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(
                    "导出会保存三个 Family、字重和全部设计轴。导入前会检查本机字体库，不会应用缺失字体的半完整方案。",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                )
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                    OutlinedButton(
                        onClick = { importLauncher.launch(arrayOf("application/json", "text/plain")) },
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.Rounded.FileUpload, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.size(6.dp))
                        Text("导入")
                    }
                    OutlinedButton(
                        onClick = { exportLauncher.launch(profileFileName()) },
                        enabled = state.slots.all { it.font != null },
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.Rounded.FileDownload, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.size(6.dp))
                        Text("导出")
                    }
                }
                if (status.isNotBlank()) {
                    Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                        Text(status, modifier = Modifier.fillMaxWidth().padding(11.dp), fontSize = 10.sp)
                    }
                }
                if (errorMessage.isNotBlank()) {
                    Surface(shape = RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.errorContainer) {
                        Row(Modifier.fillMaxWidth().padding(11.dp), verticalAlignment = Alignment.Top) {
                            Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.size(7.dp))
                            Text(errorMessage, modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer, fontSize = 10.sp)
                        }
                    }
                }
            }
        },
        confirmButton = {
            val profile = pendingProfile
            if (profile != null) {
                TextButton(
                    onClick = {
                        applyStudioProfile(profile, actions)
                        pendingProfile = null
                        status = "方案已载入到字体工坊，生成前仍可继续调整"
                    },
                ) { Text("应用方案", fontWeight = FontWeight.Black) }
            } else {
                TextButton(onClick = onDismiss) { Text("完成") }
            }
        },
        dismissButton = {
            if (pendingProfile != null) TextButton(onClick = { pendingProfile = null }) { Text("取消导入") }
        },
    )
}

private fun normalizedProfileAxes(axes: Map<String, Float>, weight: Int): Map<String, Float> = buildMap {
    axes.entries.take(16).forEach { (tag, value) ->
        if (tag.length == 4 && value.isFinite()) put(tag, if (tag == "wght") value.coerceIn(1f, 1000f) else value)
    }
    put("wght", (get("wght") ?: weight.toFloat()).coerceIn(1f, 1000f))
}

private fun readProfileText(contentResolver: android.content.ContentResolver, uri: Uri): String {
    contentResolver.openInputStream(uri)?.use { input ->
        BufferedReader(InputStreamReader(input, Charsets.UTF_8)).use { reader ->
            val output = StringBuilder()
            val buffer = CharArray(4096)
            while (true) {
                val count = reader.read(buffer)
                if (count < 0) break
                output.append(buffer, 0, count)
                if (output.length > STUDIO_PROFILE_MAX_CHARS) throw IllegalArgumentException("方案文件过大")
            }
            return output.toString()
        }
    }
    throw IllegalStateException("无法打开方案文件")
}

private fun profileFileName(): String {
    val timestamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
    return "LuoShu-profile-$timestamp.json"
}

private val MixSlot.profileKey: String
    get() = when (this) {
        MixSlot.Cjk -> "cjk"
        MixSlot.Latin -> "latin"
        MixSlot.Digit -> "digit"
    }

private val MixSlot.profileLabel: String
    get() = when (this) {
        MixSlot.Cjk -> "中文"
        MixSlot.Latin -> "英文"
        MixSlot.Digit -> "数字"
    }
