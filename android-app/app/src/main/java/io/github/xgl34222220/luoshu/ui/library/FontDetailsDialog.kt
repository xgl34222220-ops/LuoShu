package io.github.xgl34222220.luoshu.ui.library

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
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
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
import io.github.xgl34222220.luoshu.ui.font.fontPreviewText
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

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
    val container = if (miuix) tokens.elevatedCardBackground else scheme.surfaceContainerHigh
    val primaryText = if (miuix) tokens.textPrimary else scheme.onSurface
    val secondaryText = if (miuix) tokens.textSecondary else scheme.onSurfaceVariant
    var deepMetadata by remember(font.id) { mutableStateOf<FontDeepMetadata?>(null) }
    var deepLoading by remember(font.id) { mutableStateOf(true) }

    LaunchedEffect(font.id) {
        deepLoading = true
        deepMetadata = loadFontDeepMetadata(font)
        deepLoading = false
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(if (miuix) 34.dp else 28.dp),
        containerColor = container,
        title = {
            Column {
                Text(
                    text = font.name,
                    color = primaryText,
                    fontSize = 23.sp,
                    lineHeight = 28.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(5.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = if (font.valid) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                        contentDescription = null,
                        tint = if (font.valid) tokens.success else scheme.error,
                    )
                    Spacer(Modifier.width(7.dp))
                    Text(
                        text = when {
                            active -> "当前正在使用"
                            font.valid -> "字体检查通过"
                            else -> "字体需要检查"
                        },
                        color = if (font.valid) tokens.success else scheme.error,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 560.dp)
                    .verticalScroll(rememberScrollState()),
            ) {
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(if (miuix) 25.dp else 20.dp),
                    color = if (miuix) tokens.cardBackground else scheme.surfaceContainer,
                ) {
                    NativeFontPreview(
                        font = font,
                        text = fontPreviewText(font, detailed = true),
                        axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(112.dp)
                            .padding(horizontal = 17.dp, vertical = 14.dp),
                        textSizeSp = 25f,
                        maxLines = 2,
                    )
                }
                Spacer(Modifier.height(16.dp))
                FontDetailLine("能力", fontCapabilityLabel(font), primaryText, secondaryText)
                FontDetailLine("格式", font.format.ifBlank { "未知" }, primaryText, secondaryText)
                FontDetailLine("大小", font.size.ifBlank { "未知" }, primaryText, secondaryText)
                FontDetailLine("导入时间", font.date.ifBlank { "未知" }, primaryText, secondaryText)
                FontDetailLine("字重", font.weightLabel, primaryText, secondaryText)
                FontDetailLine("中文覆盖", if (font.supportsCjk) "完整" else "不完整，仅建议作为英文字体", primaryText, secondaryText)
                FontDetailLine("字体 ID", font.id, primaryText, secondaryText)
                if (!font.valid && font.error.isNotBlank()) {
                    Spacer(Modifier.height(11.dp))
                    Surface(
                        shape = RoundedCornerShape(18.dp),
                        color = scheme.errorContainer,
                    ) {
                        Text(
                            text = font.error,
                            modifier = Modifier.padding(13.dp),
                            color = scheme.onErrorContainer,
                            fontSize = 12.sp,
                        )
                    }
                }

                Spacer(Modifier.height(18.dp))
                Text(
                    "字体内部信息",
                    color = primaryText,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Black,
                )
                Text(
                    "自动读取字体面、内部名称、SHA-256、字形覆盖、推荐角色和可变轴。",
                    color = secondaryText,
                    fontSize = 10.sp,
                )
                Spacer(Modifier.height(10.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(if (miuix) 22.dp else 18.dp),
                    color = if (miuix) tokens.cardBackground else scheme.surfaceContainer,
                ) {
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
        },
        confirmButton = {
            if (!active) {
                Button(
                    onClick = onApply,
                    enabled = font.valid && !busy,
                ) {
                    Text("应用字体", fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("关闭")
            }
        },
    )
}

@Composable
private fun FontDetailLine(
    label: String,
    value: String,
    primaryText: Color,
    secondaryText: Color,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 9.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            text = label,
            modifier = Modifier.width(76.dp),
            color = secondaryText,
            fontSize = 11.sp,
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
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f))
}
