package io.github.xgl34222220.luoshu

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
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
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val DETAILS_BRIDGE = "/data/adb/modules/LuoShu/common/font_details.sh"

private data class DetailedFontMetadata(
    val title: String,
    val text: String,
)

@Composable
internal fun FontMetadataInspector(
    viewModel: LuoShuViewModel,
    style: UiStyle,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var showPicker by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var details by remember { mutableStateOf<DetailedFontMetadata?>(null) }
    val tokens = LocalMiuixTokens.current

    Surface(
        onClick = { showPicker = true },
        enabled = viewModel.snapshot.installed && viewModel.fonts.isNotEmpty() && !busy,
        modifier = modifier.size(if (style == UiStyle.MIUIX) 54.dp else 52.dp),
        shape = if (style == UiStyle.MIUIX) RoundedCornerShape(19.dp) else CircleShape,
        color = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surface.copy(alpha = .96f),
        contentColor = MaterialTheme.colorScheme.primary,
        shadowElevation = if (style == UiStyle.MIUIX) 16.dp else 12.dp,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .10f)),
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp)
            } else {
                Icon(Icons.Rounded.Info, contentDescription = "深度分析字体")
            }
        }
    }

    if (showPicker) {
        MetadataPickerDialog(
            style = style,
            fonts = viewModel.fonts,
            onDismiss = { showPicker = false },
            onChoose = { font ->
                showPicker = false
                busy = true
                scope.launch {
                    details = withContext(Dispatchers.IO) { loadDetailedFontMetadata(font) }
                    busy = false
                }
            },
        )
    }

    if (busy) {
        AlertDialog(
            onDismissRequest = {},
            title = { Text("正在分析字体", fontWeight = FontWeight.Black) },
            text = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(12.dp))
                    Text("正在读取内部名称、字重、覆盖范围和可变轴…")
                }
            },
            confirmButton = {},
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            containerColor = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh,
        )
    }

    details?.let { result ->
        MetadataResultDialog(
            style = style,
            result = result,
            onDismiss = { details = null },
        )
    }
}

@Composable
private fun MetadataPickerDialog(
    style: UiStyle,
    fonts: List<FontItem>,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    var query by remember { mutableStateOf("") }
    val filtered = remember(fonts, query) {
        val needle = query.trim()
        if (needle.isBlank()) fonts else fonts.filter { font ->
            font.name.contains(needle, ignoreCase = true) ||
                font.format.contains(needle, ignoreCase = true) ||
                font.weightLabel.contains(needle, ignoreCase = true)
        }
    }
    val tokens = LocalMiuixTokens.current

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("选择字体进行深度分析", fontWeight = FontWeight.Black) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 20.dp else 16.dp),
                    leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                    placeholder = { Text("搜索字体") },
                )
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 420.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    items(filtered, key = { it.id }) { font ->
                        Surface(
                            modifier = Modifier.fillMaxWidth().clickable { onChoose(font) },
                            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 24.dp else 18.dp),
                            color = if (style == UiStyle.MIUIX) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow,
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Surface(
                                    modifier = Modifier.size(44.dp),
                                    shape = RoundedCornerShape(15.dp),
                                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                                ) {
                                    Box(contentAlignment = Alignment.Center) {
                                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                                    }
                                }
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(font.name, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                                    Text(
                                        listOf(font.format, font.size, font.weightLabel).filter { it.isNotBlank() }.joinToString(" · "),
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        fontSize = 10.sp,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        containerColor = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh,
    )
}

@Composable
private fun MetadataResultDialog(
    style: UiStyle,
    result: DetailedFontMetadata,
    onDismiss: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(result.title, fontWeight = FontWeight.Black, maxLines = 2) },
        text = {
            SelectionContainer {
                LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 500.dp)) {
                    item {
                        Text(
                            result.text,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            lineHeight = 18.sp,
                        )
                    }
                }
            }
        },
        confirmButton = { Button(onClick = onDismiss) { Text("完成") } },
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        containerColor = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh,
    )
}

private suspend fun loadDetailedFontMetadata(font: FontItem): DetailedFontMetadata {
    return try {
        val result = RootShell.exec(
            "sh ${RootShell.quote(DETAILS_BRIDGE)} ${RootShell.quote(font.id)}",
            timeoutMs = 60_000L,
        )
        if (result.code != 0) error(result.stderr.ifBlank { "字体详情读取失败" })
        val root = firstMetadataJson(result.stdout)
        if (root.optString("status") != "ok") error(root.optString("message", "字体详情读取失败"))
        val data = root.getJSONObject("data")
        val faces = data.getJSONArray("faces")
        val title = faces.optJSONObject(0)?.optString("fullName", font.name).orEmpty().ifBlank { font.name }
        val text = buildString {
            append("文件：").append(data.optString("fileName")).append('\n')
            append("SHA-256：").append(data.optString("sha256")).append('\n')
            append("稳定文件 ID：").append(data.optString("fileUid")).append('\n')
            append("字体面数量：").append(data.optInt("faceCount", faces.length())).append('\n')
            append("文件大小：").append(formatMetadataBytes(data.optLong("bytes"))).append("\n\n")
            for (index in 0 until faces.length()) {
                val face = faces.optJSONObject(index) ?: continue
                val coverage = face.optJSONObject("coverage")
                val roles = coverage?.optJSONObject("roles")
                append("字体面 #").append(face.optInt("faceIndex", index)).append('\n')
                append("  名称：").append(face.optString("fullName", face.optString("family"))).append('\n')
                append("  Family：").append(face.optString("family")).append('\n')
                append("  Subfamily：").append(face.optString("subfamily")).append('\n')
                face.optString("postScriptName").takeIf { it.isNotBlank() }?.let {
                    append("  PostScript：").append(it).append('\n')
                }
                append("  稳定 ID：").append(face.optString("uid")).append('\n')
                append("  格式：").append(face.optString("format"))
                    .append(" · 字重 ").append(face.optInt("weight", 400))
                    .append(if (face.optBoolean("italic")) " · 斜体" else " · 正体")
                    .append('\n')
                append("  字形：").append(face.optInt("glyphs"))
                    .append(" · Unicode：").append(coverage?.optInt("codepoints") ?: 0)
                    .append(" · CJK：").append(coverage?.optInt("cjkCount") ?: 0)
                    .append('\n')
                val roleLabels = buildList {
                    if (roles?.optBoolean("cjk") == true) add("中文基底")
                    if (roles?.optBoolean("latin") == true) add("英文")
                    if (roles?.optBoolean("digit") == true) add("数字")
                }
                append("  推荐角色：")
                    .append(if (roleLabels.isEmpty()) "不满足完整角色门禁" else roleLabels.joinToString("、"))
                    .append('\n')
                val axes = face.optJSONArray("axes")
                if (axes != null && axes.length() > 0) {
                    append("  可变轴：")
                    for (axisIndex in 0 until axes.length()) {
                        val axis = axes.optJSONObject(axisIndex) ?: continue
                        if (axisIndex > 0) append("；")
                        append(axis.optString("tag"))
                            .append(' ')
                            .append(trimMetadataNumber(axis.optDouble("min")))
                            .append("–")
                            .append(trimMetadataNumber(axis.optDouble("max")))
                            .append("，默认 ")
                            .append(trimMetadataNumber(axis.optDouble("default")))
                    }
                    append('\n')
                } else {
                    append("  可变轴：无\n")
                }
                if (index < faces.length() - 1) append('\n')
            }
        }.trimEnd()
        DetailedFontMetadata(title, text)
    } catch (error: Throwable) {
        DetailedFontMetadata(font.name, error.message ?: "字体详情读取失败")
    }
}

private fun firstMetadataJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("模块没有返回 JSON 数据")
    return JSONObject(line.trim())
}

private fun formatMetadataBytes(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "%.1f KB".format(bytes / 1024.0)
    bytes < 1024L * 1024L * 1024L -> "%.1f MB".format(bytes / 1024.0 / 1024.0)
    else -> "%.2f GB".format(bytes / 1024.0 / 1024.0 / 1024.0)
}

private fun trimMetadataNumber(value: Double): String {
    val rounded = value.toLong()
    return if (value == rounded.toDouble()) rounded.toString()
    else "%.2f".format(value).trimEnd('0').trimEnd('.')
}
