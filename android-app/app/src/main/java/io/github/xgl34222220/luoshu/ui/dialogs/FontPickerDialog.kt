package io.github.xgl34222220.luoshu.ui.dialogs

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.selection.selectable
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
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSmoothShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import android.view.Gravity
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.font.resolveAndCacheFontDefaultAxes
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

@Composable
internal fun FontPickerDialogRoute(
    style: UiStyle,
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var resolvingId by remember(slot) { mutableStateOf<String?>(null) }
    var errorMessage by remember(slot) { mutableStateOf<String?>(null) }
    val choose: (FontItem) -> Unit = { font ->
        if (resolvingId == null) {
            resolvingId = font.id
            errorMessage = null
            scope.launch {
                val resolved = try {
                    resolveAndCacheFontDefaultAxes(font)
                    true
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    errorMessage = "读取字体信息失败，请重试。"
                    false
                } finally {
                    resolvingId = null
                }
                if (resolved) onChoose(font)
            }
        }
    }
    MiuixFontPickerDialog(slot, fonts, selected, resolvingId, errorMessage, onDismiss, choose)
}

@Composable
private fun MiuixFontPickerDialog(
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    resolvingId: String?,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    var query by rememberSaveable(slot) { mutableStateOf("") }
    val filtered = remember(fonts, query) { filterFonts(fonts, query) }
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 660.dp),
            shape = LuoShuSmoothShape(32.dp),
            color = tokens.elevatedCardBackground,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f)),
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "选择${slotLabel(slot)}字体",
                            color = tokens.textPrimary,
                            fontSize = 22.sp,
                            lineHeight = 30.sp,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Text(
                        "${filtered.size} 个",
                        color = tokens.textSecondary,
                        fontSize = 12.sp,
                    )
                }

                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = LuoShuSmoothShape(20.dp),
                    leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                    placeholder = { Text("搜索名称、格式或字重") },
                )

                errorMessage?.let {
                    Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp, lineHeight = 18.sp)
                }

                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f, fill = false)
                        .heightIn(min = 72.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    if (filtered.isEmpty()) {
                        item {
                            Text(
                                if (query.isBlank()) "暂无可选字体，请先导入字体。" else "没有找到匹配的字体。",
                                modifier = Modifier.fillMaxWidth().padding(vertical = 20.dp),
                                color = tokens.textSecondary,
                                fontSize = 14.sp,
                            )
                        }
                    }
                    items(filtered, key = { it.id }) { font ->
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(LuoShuSmoothShape(22.dp))
                                .selectable(
                                    selected = font.id == selected,
                                    enabled = resolvingId == null,
                                    role = Role.RadioButton,
                                    onClick = { onChoose(font) },
                                ),
                            shape = LuoShuSmoothShape(22.dp),
                            color = if (font.id == selected) {
                                MaterialTheme.colorScheme.primary.copy(alpha = .09f)
                            } else {
                                tokens.cardBackground
                            },
                            border = BorderStroke(1.dp, if (font.id == selected) MaterialTheme.colorScheme.primary.copy(alpha = .25f) else MaterialTheme.colorScheme.outlineVariant.copy(alpha = .35f)),
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 15.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Surface(
                                    modifier = Modifier.size(46.dp),
                                    shape = LuoShuSmoothShape(16.dp),
                                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                                ) {
                                    Box(contentAlignment = Alignment.Center) {
                                        val glyph = when (slot) {
                                            MixSlot.Cjk -> "中"
                                            MixSlot.Latin -> "Aa"
                                            MixSlot.Digit -> "123"
                                        }
                                        if (font.valid) {
                                            NativeFontPreview(
                                                font = font,
                                                text = glyph,
                                                axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                                                modifier = Modifier.size(46.dp).padding(6.dp),
                                                textSizeSp = if (slot == MixSlot.Digit) 11f else 16f,
                                                gravity = Gravity.CENTER,
                                                maxLines = 1,
                                            )
                                        } else {
                                            Text(
                                                glyph,
                                                color = MaterialTheme.colorScheme.primary,
                                                fontWeight = FontWeight.Black,
                                                fontSize = if (slot == MixSlot.Digit) 11.sp else 16.sp,
                                            )
                                        }
                                    }
                                }
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        font.name,
                                        color = tokens.textPrimary,
                                        fontWeight = FontWeight.SemiBold,
                                        maxLines = 2,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                    Text(
                                        listOf(font.format, font.weightLabel).filter { it.isNotBlank() }.joinToString(" · "),
                                        color = tokens.textSecondary,
                                        fontSize = 12.sp,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                                if (font.id == resolvingId) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(24.dp),
                                        strokeWidth = 2.dp,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                } else if (font.id == selected) {
                                    Icon(
                                        Icons.Rounded.CheckCircle,
                                        contentDescription = null,
                                        tint = MaterialTheme.colorScheme.primary,
                                    )
                                }
                            }
                        }
                    }
                }

                OutlinedButton(
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    shape = LuoShuSmoothShape(18.dp),
                ) {
                    Text("关闭", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

private fun filterFonts(fonts: List<FontItem>, query: String): List<FontItem> {
    val needle = query.trim()
    if (needle.isBlank()) return fonts
    return fonts.filter { font ->
        font.name.contains(needle, ignoreCase = true) ||
            font.format.contains(needle, ignoreCase = true) ||
            font.weightLabel.contains(needle, ignoreCase = true)
    }
}

private fun slotLabel(slot: MixSlot): String = when (slot) {
    MixSlot.Cjk -> "中文"
    MixSlot.Latin -> "英文"
    MixSlot.Digit -> "数字"
}
