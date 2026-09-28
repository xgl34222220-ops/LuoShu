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
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLoadingSkeleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private const val DETAILS_BRIDGE = "/data/adb/modules/LuoShu/common/font_details.sh"

private data class DetailedFontMetadata(
    val title: String,
    val text: String,
    val error: String = "",
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
        modifier = modifier.size(52.dp),
        shape = if (style == UiStyle.MIUIX) RoundedCornerShape(18.dp) else CircleShape,
        color = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surface.copy(alpha = .96f),
        contentColor = MaterialTheme.colorScheme.primary,
        shadowElevation = if (style == UiStyle.MIUIX) 16.dp else 12.dp,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .10f)),
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(LuoShuIconTokens.CompactProgress), strokeWidth = 2.dp)
            } else {
                LuoShuGlyph(
                    imageVector = Icons.Rounded.Info,
                    contentDescription = "深度分析字体",
                    size = LuoShuIconTokens.ToolGlyph,
                    opticalScale = .98f,
                )
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
                Column(
                    modifier = Modifier.fillMaxWidth().heightIn(min = 104.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    LuoShuLoadingSkeleton(Modifier.fillMaxWidth(.46f).heightIn(min = 16.dp))
                    LuoShuLoadingSkeleton(Modifier.fillMaxWidth().heightIn(min = 38.dp), shape = RoundedCornerShape(14.dp))
                    LuoShuLoadingSkeleton(Modifier.fillMaxWidth(.78f).heightIn(min = 16.dp))
                }
            },
            confirmButton = {},
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            containerColor = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surface,
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
    val scheme = MaterialTheme.colorScheme
    val sections = remember(result.text) { parseMetadataSections(result.text) }
    val rows = remember(sections) { sections.flatMap { it.rows } }
    val formatValue = rows.firstOrNull { it.label == "格式" }?.value
        ?.substringBefore("·")?.trim().orEmpty().ifBlank { "未知" }
    val weightValue = rows.firstOrNull { it.label == "格式" }?.value
        ?.substringAfter("字重", "")?.substringBefore("·")?.trim().orEmpty().ifBlank {
            rows.firstOrNull { it.label == "Subfamily" }?.value.orEmpty().ifBlank { "—" }
        }
    val glyphValue = rows.firstOrNull { it.label == "字形" }?.value.orEmpty()
    val unicodeValue = Regex("""Unicode：?(\d+)""").find(glyphValue)?.groupValues?.getOrNull(1) ?: "—"
    val charsetValue = rows.firstOrNull { it.label == "推荐角色" }?.value.orEmpty().ifBlank { "—" }
    val sha = rows.firstOrNull { it.label.equals("SHA-256", ignoreCase = true) }?.value.orEmpty()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(result.title, fontWeight = FontWeight.SemiBold, maxLines = 2) },
        text = {
            if (result.error.isNotBlank()) {
                Text(result.error, color = scheme.error)
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().heightIn(max = 560.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            MetadataMetricCard("格式", formatValue, Modifier.weight(1f))
                            MetadataMetricCard("字重", weightValue, Modifier.weight(1f))
                        }
                    }
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            MetadataMetricCard("字符集", charsetValue, Modifier.weight(1f))
                            MetadataMetricCard("Unicode", unicodeValue, Modifier.weight(1f))
                        }
                    }
                    if (sha.isNotBlank()) {
                        item { MetadataHashCard(sha) }
                    }
                    items(sections, key = { it.title }) { section ->
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(18.dp),
                            color = scheme.surfaceContainerLow,
                            border = BorderStroke(0.5.dp, scheme.outlineVariant.copy(alpha = .38f)),
                        ) {
                            Column(Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 10.dp)) {
                                Text(section.title, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                                Spacer(Modifier.size(4.dp))
                                section.rows
                                    .filterNot { it.label.equals("SHA-256", ignoreCase = true) }
                                    .forEachIndexed { index, row ->
                                        Row(
                                            modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                                            verticalAlignment = Alignment.Top,
                                        ) {
                                            Text(
                                                row.label,
                                                modifier = Modifier.width(84.dp),
                                                color = scheme.onSurfaceVariant,
                                                fontSize = 11.sp,
                                            )
                                            Text(
                                                row.value.ifBlank { "—" },
                                                modifier = Modifier.weight(1f),
                                                color = scheme.onSurface,
                                                fontSize = 11.5.sp,
                                                lineHeight = 16.sp,
                                                fontFamily = if (
                                                    row.label.contains("ID", true) ||
                                                    row.label.contains("PostScript", true)
                                                ) FontFamily.Monospace else FontFamily.Default,
                                            )
                                        }
                                        if (index < section.rows.lastIndex) {
                                            HorizontalDivider(color = scheme.outlineVariant.copy(alpha = .22f))
                                        }
                                    }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { Button(onClick = onDismiss) { Text("完成") } },
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
        containerColor = if (style == UiStyle.MIUIX) tokens.elevatedCardBackground else scheme.surface,
    )
}

private data class MetadataDisplayRow(
    val label: String,
    val value: String,
)

private data class MetadataDisplaySection(
    val title: String,
    val rows: List<MetadataDisplayRow>,
)

private fun parseMetadataSections(text: String): List<MetadataDisplaySection> {
    val sections = mutableListOf<MetadataDisplaySection>()
    var title = "文件信息"
    var rows = mutableListOf<MetadataDisplayRow>()

    fun flush() {
        if (rows.isNotEmpty()) {
            sections += MetadataDisplaySection(title, rows.toList())
            rows = mutableListOf()
        }
    }

    text.lineSequence().forEach { raw ->
        val line = raw.trim()
        if (line.isBlank()) return@forEach
        if (line.startsWith("字体面 #")) {
            flush()
            title = line
            return@forEach
        }
        val separator = line.indexOf('：')
        if (separator > 0) {
            rows += MetadataDisplayRow(
                label = line.substring(0, separator).trim(),
                value = line.substring(separator + 1).trim(),
            )
        } else {
            rows += MetadataDisplayRow("信息", line)
        }
    }
    flush()
    return sections
}

@Composable
private fun MetadataMetricCard(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(15.dp),
        color = scheme.primary.copy(alpha = .07f),
    ) {
        Column(Modifier.padding(horizontal = 11.dp, vertical = 9.dp)) {
            Text(label, color = scheme.onSurfaceVariant, fontSize = 10.sp)
            Text(
                value,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun MetadataHashCard(sha: String) {
    val scheme = MaterialTheme.colorScheme
    val clipboard = LocalClipboardManager.current
    val display = if (sha.length > 16) "${sha.take(8)}…${sha.takeLast(6)}" else sha
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(15.dp),
        color = scheme.surfaceContainerHigh,
        border = BorderStroke(0.5.dp, scheme.outlineVariant.copy(alpha = .38f)),
    ) {
        Row(
            modifier = Modifier.padding(start = 12.dp, top = 8.dp, bottom = 8.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("SHA-256", color = scheme.onSurfaceVariant, fontSize = 10.sp)
                Text(display, fontFamily = FontFamily.Monospace, fontSize = 12.sp)
            }
            IconButton(
                onClick = { clipboard.setText(AnnotatedString(sha)) },
                modifier = Modifier.size(38.dp),
            ) {
                Icon(
                    Icons.Rounded.ContentCopy,
                    contentDescription = "复制 SHA-256",
                    modifier = Modifier.size(17.dp),
                )
            }
        }
    }
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
        DetailedFontMetadata(
            title = font.name,
            text = "",
            error = error.message ?: "字体详情读取失败",
        )
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
