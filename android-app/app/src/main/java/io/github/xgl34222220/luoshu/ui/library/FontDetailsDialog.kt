package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

private enum class FontPreviewMode(val label: String) {
    Mixed("综合"),
    Cjk("中文"),
    Latin("English"),
    Numbers("数字"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun FontDetailsDialogRoute(
    style: UiStyle,
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    onDismiss: () -> Unit,
    onApply: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    val tokens = LocalMiuixTokens.current
    val miuix = style == UiStyle.MIUIX
    val container = if (miuix) tokens.cardBackground else scheme.surface
    val elevated = if (miuix) tokens.elevatedCardBackground else scheme.surfaceContainerHigh
    val primaryText = if (miuix) tokens.textPrimary else scheme.onSurface
    val secondaryText = if (miuix) tokens.textSecondary else scheme.onSurfaceVariant
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var deepMetadata by remember(font.id) { mutableStateOf<FontDeepMetadata?>(null) }
    var deepLoading by remember(font.id) { mutableStateOf(true) }
    var metadataExpanded by rememberSaveable(font.id) { mutableStateOf(false) }
    var previewMode by remember(font.id) { mutableStateOf(FontPreviewMode.Mixed) }

    LaunchedEffect(font.id) {
        deepLoading = true
        deepMetadata = loadFontDeepMetadata(font)
        deepLoading = false
    }

    val previewModes = remember(font.id, font.supportsCjk) {
        buildList {
            add(FontPreviewMode.Mixed)
            if (font.supportsCjk) add(FontPreviewMode.Cjk)
            add(FontPreviewMode.Latin)
            add(FontPreviewMode.Numbers)
        }
    }
    val previewText = when (previewMode) {
        FontPreviewMode.Mixed -> if (font.supportsCjk) {
            "花间一壶酒\nLuoShu Aa 0123456789"
        } else {
            "LuoShu Typeface\nAa 0123456789"
        }
        FontPreviewMode.Cjk -> "花间一壶酒\n天地玄黄 宇宙洪荒"
        FontPreviewMode.Latin -> "The quick brown fox\nLuoShu Typeface"
        FontPreviewMode.Numbers -> "0123456789\n¥ 123,456.78"
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp),
        containerColor = container,
        dragHandle = {
            Surface(
                modifier = Modifier.padding(top = 10.dp).width(36.dp).height(4.dp),
                shape = RoundedCornerShape(999.dp),
                color = secondaryText.copy(alpha = .24f),
            ) {}
        },
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 760.dp)
                .verticalScroll(rememberScrollState())
                .padding(start = 20.dp, end = 20.dp, bottom = 28.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        text = font.name,
                        color = primaryText,
                        fontSize = 24.sp,
                        lineHeight = 29.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(6.dp))
                    FontStateBadge(
                        text = when {
                            active -> "当前正在使用"
                            font.valid -> "字体检查通过"
                            else -> "字体需要检查"
                        },
                        color = if (font.valid) tokens.success else scheme.error,
                        valid = font.valid,
                    )
                }
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Rounded.Close, contentDescription = "关闭字体详情", tint = secondaryText)
                }
            }

            Spacer(Modifier.height(16.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(26.dp),
                color = elevated,
            ) {
                NativeFontPreview(
                    font = font,
                    text = previewText,
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(158.dp)
                        .padding(horizontal = 20.dp, vertical = 18.dp),
                    textSizeSp = 27f,
                    maxLines = 2,
                )
            }

            Spacer(Modifier.height(11.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                previewModes.forEach { mode ->
                    PreviewModeChip(
                        label = mode.label,
                        active = previewMode == mode,
                        onClick = { previewMode = mode },
                    )
                }
            }

            Spacer(Modifier.height(18.dp))
            Text("字体信息", color = primaryText, fontSize = 16.sp, fontWeight = FontWeight.Black)
            Text("快速查看这款字体的能力、字重与文件信息", color = secondaryText, fontSize = 10.sp)
            Spacer(Modifier.height(9.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(22.dp),
                color = elevated,
            ) {
                Column(Modifier.padding(horizontal = 15.dp, vertical = 6.dp)) {
                    FontDetailLine("能力", fontCapabilityLabel(font), primaryText, secondaryText)
                    FontDetailLine("字重", font.weightLabel, primaryText, secondaryText)
                    FontDetailLine("覆盖", if (font.supportsCjk) "中日韩 · 拉丁 · 数字" else "拉丁 · 数字", primaryText, secondaryText)
                    FontDetailLine("格式", font.format.ifBlank { "未知" }, primaryText, secondaryText)
                    FontDetailLine("大小", font.size.ifBlank { "未知" }, primaryText, secondaryText)
                    FontDetailLine("导入", font.date.ifBlank { "未知" }, primaryText, secondaryText)
                    FontDetailLine("字体 ID", font.id, primaryText, secondaryText, divider = false)
                }
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(12.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(18.dp),
                    color = scheme.errorContainer,
                ) {
                    Row(
                        modifier = Modifier.padding(14.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Icon(Icons.Rounded.Warning, contentDescription = null, tint = scheme.error)
                        Spacer(Modifier.width(9.dp))
                        Text(
                            text = font.error,
                            modifier = Modifier.weight(1f),
                            color = scheme.onErrorContainer,
                            fontSize = 11.sp,
                        )
                    }
                }
            }

            Spacer(Modifier.height(16.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(22.dp),
                color = elevated,
            ) {
                Column {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { metadataExpanded = !metadataExpanded }
                            .padding(horizontal = 15.dp, vertical = 13.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("字体内部信息", color = primaryText, fontSize = 14.sp, fontWeight = FontWeight.Black)
                            Text("内部名称、SHA-256、字形覆盖与可变轴", color = secondaryText, fontSize = 10.sp)
                        }
                        Icon(
                            if (metadataExpanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                            contentDescription = null,
                            tint = secondaryText,
                        )
                    }
                    if (metadataExpanded) {
                        HorizontalDivider(color = scheme.outlineVariant.copy(alpha = .42f))
                        when {
                            deepLoading -> {
                                Row(
                                    modifier = Modifier.padding(16.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                                    Spacer(Modifier.width(11.dp))
                                    Text("正在分析字体内部结构…", color = secondaryText, fontSize = 12.sp)
                                }
                            }
                            deepMetadata?.error?.isNotBlank() == true -> {
                                Row(
                                    modifier = Modifier.padding(15.dp),
                                    verticalAlignment = Alignment.Top,
                                ) {
                                    Icon(Icons.Rounded.Warning, contentDescription = null, tint = scheme.error)
                                    Spacer(Modifier.width(9.dp))
                                    Text(
                                        deepMetadata?.error.orEmpty(),
                                        modifier = Modifier.weight(1f),
                                        color = scheme.error,
                                        fontSize = 11.sp,
                                    )
                                }
                            }
                            else -> {
                                SelectionContainer {
                                    Text(
                                        text = deepMetadata?.text.orEmpty(),
                                        modifier = Modifier.padding(15.dp),
                                        color = primaryText,
                                        fontSize = 10.sp,
                                        lineHeight = 16.sp,
                                        fontFamily = FontFamily.Monospace,
                                    )
                                }
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(18.dp))
            if (active) {
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(18.dp),
                    color = tokens.success.copy(alpha = .11f),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = tokens.success)
                        Spacer(Modifier.width(8.dp))
                        Text("当前正在使用", color = tokens.success, fontWeight = FontWeight.Black)
                    }
                }
            } else {
                Button(
                    onClick = onApply,
                    enabled = font.valid && !busy,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                    shape = RoundedCornerShape(17.dp),
                ) {
                    Text("应用此字体", fontSize = 14.sp, fontWeight = FontWeight.Black)
                }
            }
        }
    }
}

@Composable
private fun FontStateBadge(text: String, color: Color, valid: Boolean) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = color.copy(alpha = .11f),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = if (valid) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                contentDescription = null,
                modifier = Modifier.size(16.dp),
                tint = color,
            )
            Spacer(Modifier.width(5.dp))
            Text(text, color = color, fontSize = 10.sp, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
private fun PreviewModeChip(label: String, active: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 7.dp),
            color = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun FontDetailLine(
    label: String,
    value: String,
    primaryText: Color,
    secondaryText: Color,
    divider: Boolean = true,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 9.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = label,
            modifier = Modifier.width(68.dp),
            color = secondaryText,
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text = value,
            modifier = Modifier.weight(1f),
            color = primaryText,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium,
        )
    }
    if (divider) {
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .36f))
    }
}
