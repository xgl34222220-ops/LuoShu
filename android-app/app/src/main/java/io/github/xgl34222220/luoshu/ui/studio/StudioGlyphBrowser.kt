package io.github.xgl34222220.luoshu.ui.studio

import android.view.Gravity
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ChevronLeft
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

private const val GLYPH_PAGE_SIZE = 32

@Immutable
internal data class GlyphBrowserCategory(
    val id: String,
    val label: String,
    val sample: String,
)

internal val glyphBrowserCategories = listOf(
    GlyphBrowserCategory("common", "常用", "永和九年岁在癸丑洛书字体排印LuoShuTypography0123456789"),
    GlyphBrowserCategory("cjk", "中文", "天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏闰余成岁律吕调阳云腾致雨露结为霜"),
    GlyphBrowserCategory("latin", "拉丁", "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝ"),
    GlyphBrowserCategory("digits", "数字", "0123456789０１２３４５６７８９+-−×÷=%‰₹¥￥€£$¢₩₽"),
    GlyphBrowserCategory("punctuation", "标点", "，。！？；：、（）【】《》“”‘’…—·,.!?;:()[]{}<>/\\@#&*_~`^|"),
    GlyphBrowserCategory("symbols", "符号", "←↑→↓↔⇒⇔√∞≈≠≤≥±∑∏∫∆Ωαβγπμ℃℉№™©®✓✕★☆◆◇○●□■"),
)

internal fun glyphCodePoints(text: String): List<Int> {
    val result = ArrayList<Int>(text.length)
    var index = 0
    while (index < text.length) {
        val codePoint = Character.codePointAt(text, index)
        result += codePoint
        index += Character.charCount(codePoint)
    }
    return result
}

internal fun glyphPage(text: String, page: Int, pageSize: Int = GLYPH_PAGE_SIZE): String {
    if (pageSize <= 0) return ""
    val points = glyphCodePoints(text)
    val from = (page.coerceAtLeast(0) * pageSize).coerceAtMost(points.size)
    val to = (from + pageSize).coerceAtMost(points.size)
    return buildString {
        points.subList(from, to).forEach { point -> appendCodePoint(point) }
    }
}

@Composable
internal fun StudioGlyphBrowserDialog(
    style: UiStyle,
    state: FontStudioUiState,
    onDismiss: () -> Unit,
) {
    var slot by rememberSaveable { mutableStateOf(MixSlot.Cjk) }
    var categoryId by rememberSaveable { mutableStateOf(glyphBrowserCategories.first().id) }
    var customText by rememberSaveable { mutableStateOf("") }
    var page by rememberSaveable { mutableIntStateOf(0) }
    val slotState = state.slots.firstOrNull { it.slot == slot }
    val category = glyphBrowserCategories.firstOrNull { it.id == categoryId } ?: glyphBrowserCategories.first()
    val source = customText.ifBlank { category.sample }
    val points = remember(source) { glyphCodePoints(source) }
    val pageCount = ((points.size + GLYPH_PAGE_SIZE - 1) / GLYPH_PAGE_SIZE).coerceAtLeast(1)
    val safePage = page.coerceIn(0, pageCount - 1)
    val visible = remember(source, safePage) { glyphPage(source, safePage) }
    val rows = remember(visible) {
        glyphCodePoints(visible).chunked(8).map { chunk ->
            buildString { chunk.forEach { point -> appendCodePoint(point) } }
        }
    }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 780.dp),
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 36.dp else 30.dp),
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
            shadowElevation = 14.dp,
        ) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 15.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(46.dp),
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.primaryContainer,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(Icons.Rounded.ListAlt, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("字形浏览器", fontSize = 20.sp, fontWeight = FontWeight.Black)
                        Text("视觉浏览不代替字形覆盖检测", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                    IconButton(onClick = onDismiss) { Icon(Icons.Rounded.Close, contentDescription = "关闭") }
                }

                Spacer(Modifier.height(12.dp))
                LazyColumn(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                    item {
                        StudioGlyphChoiceRow(
                            labels = listOf(
                                MixSlot.Cjk to "中文槽",
                                MixSlot.Latin to "英文槽",
                                MixSlot.Digit to "数字槽",
                            ),
                            selected = slot,
                            onSelected = { slot = it; page = 0 },
                        )
                    }
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                            horizontalArrangement = Arrangement.spacedBy(7.dp),
                        ) {
                            glyphBrowserCategories.forEach { option ->
                                StudioGlyphPill(
                                    label = option.label,
                                    active = option.id == category.id && customText.isBlank(),
                                    onClick = {
                                        categoryId = option.id
                                        customText = ""
                                        page = 0
                                    },
                                )
                            }
                        }
                    }
                    item {
                        OutlinedTextField(
                            value = customText,
                            onValueChange = {
                                customText = it.take(256)
                                page = 0
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(20.dp),
                            minLines = 1,
                            maxLines = 3,
                            label = { Text("自定义字符，可留空使用分类样本") },
                        )
                    }
                    item {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(24.dp),
                            color = MaterialTheme.colorScheme.surfaceContainerLow,
                        ) {
                            Column(Modifier.padding(horizontal = 14.dp, vertical = 13.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Column(Modifier.weight(1f)) {
                                        Text(slotState?.font?.name ?: "当前槽位未选择字体", fontWeight = FontWeight.Black, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                        Text(
                                            "${slotState?.weight ?: 400} · 第 ${safePage + 1}/$pageCount 页 · ${points.size} 个字符",
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            fontSize = 9.sp,
                                        )
                                    }
                                    IconButton(onClick = { page = (safePage - 1).coerceAtLeast(0) }, enabled = safePage > 0) {
                                        Icon(Icons.Rounded.ChevronLeft, contentDescription = "上一页")
                                    }
                                    IconButton(onClick = { page = (safePage + 1).coerceAtMost(pageCount - 1) }, enabled = safePage < pageCount - 1) {
                                        Icon(Icons.Rounded.ChevronRight, contentDescription = "下一页")
                                    }
                                }
                                Spacer(Modifier.height(8.dp))
                                if (slotState?.font == null || visible.isEmpty()) {
                                    Text(
                                        if (visible.isEmpty()) "没有可浏览字符" else "请先为该槽位选择字体",
                                        modifier = Modifier.fillMaxWidth().padding(vertical = 24.dp),
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                } else {
                                    rows.forEach { row ->
                                        NativeFontPreview(
                                            font = slotState.font,
                                            text = row,
                                            axes = slotState.axes,
                                            modifier = Modifier.fillMaxWidth().height(58.dp),
                                            textSizeSp = 29f,
                                            gravity = Gravity.CENTER,
                                            maxLines = 1,
                                        )
                                    }
                                }
                            }
                        }
                    }
                    item {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(20.dp),
                            color = MaterialTheme.colorScheme.surfaceContainer,
                        ) {
                            Text(
                                text = glyphCodePointLabels(visible),
                                modifier = Modifier.fillMaxWidth().padding(12.dp),
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 9.sp,
                                lineHeight = 14.sp,
                            )
                        }
                    }
                }
                TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) {
                    Text("完成", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun <T> StudioGlyphChoiceRow(
    labels: List<Pair<T, String>>,
    selected: T,
    onSelected: (T) -> Unit,
) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        labels.forEach { (value, label) ->
            StudioGlyphPill(
                label = label,
                active = value == selected,
                onClick = { onSelected(value) },
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun StudioGlyphPill(
    label: String,
    active: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainer,
        contentColor = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
            fontSize = 10.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
    }
}

private fun glyphCodePointLabels(text: String): String {
    val points = glyphCodePoints(text)
    if (points.isEmpty()) return "暂无 Unicode 码位"
    return points.joinToString("  ") { point ->
        val value = String(Character.toChars(point))
        "$value U+${point.toString(16).uppercase().padStart(4, '0')}"
    }
}
