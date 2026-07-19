package io.github.xgl34222220.luoshu.ui.dialogs

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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material3.AlertDialog
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun FontPickerDialogRoute(
    style: UiStyle,
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    when (style) {
        UiStyle.MATERIAL -> MaterialFontPickerDialog(slot, fonts, selected, onDismiss, onChoose)
        UiStyle.MIUIX -> MiuixFontPickerDialog(slot, fonts, selected, onDismiss, onChoose)
    }
}

@Composable
private fun MaterialFontPickerDialog(
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    var query by remember(slot) { mutableStateOf("") }
    val filtered = remember(fonts, query) { filterFonts(fonts, query) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Column {
                Text("选择${slotLabel(slot)}字体", fontWeight = FontWeight.Black)
                Text(
                    "${filtered.size} 个可用字体",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                )
            }
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = MaterialTheme.shapes.large,
                    leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                    placeholder = { Text("搜索名称、格式或字重") },
                )
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 420.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(filtered, key = { it.id }) { font ->
                        MaterialFontPickerItem(font, font.id == selected) { onChoose(font) }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } },
        shape = MaterialTheme.shapes.extraLarge,
    )
}

@Composable
private fun MaterialFontPickerItem(
    font: FontItem,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .clickable(onClick = onClick),
        shape = MaterialTheme.shapes.large,
        color = if (selected) {
            MaterialTheme.colorScheme.primaryContainer
        } else {
            MaterialTheme.colorScheme.surfaceContainerLow
        },
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(44.dp),
                shape = MaterialTheme.shapes.medium,
                color = MaterialTheme.colorScheme.tertiaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("Aa", fontWeight = FontWeight.Black, color = MaterialTheme.colorScheme.tertiary)
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(font.name, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(
                    listOf(font.format, font.weightLabel).filter { it.isNotBlank() }.joinToString(" · "),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 10.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (selected) {
                Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

@Composable
private fun MiuixFontPickerDialog(
    slot: MixSlot,
    fonts: List<FontItem>,
    selected: String,
    onDismiss: () -> Unit,
    onChoose: (FontItem) -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    var query by remember(slot) { mutableStateOf("") }
    val filtered = remember(fonts, query) { filterFonts(fonts, query) }
    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(38.dp),
            color = tokens.elevatedCardBackground,
            shadowElevation = 20.dp,
        ) {
            Column(
                modifier = Modifier.padding(18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Row(verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "FONT SOURCE",
                            color = MaterialTheme.colorScheme.primary,
                            fontSize = 9.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 2.sp,
                        )
                        Text(
                            "选择${slotLabel(slot)}字体",
                            color = tokens.textPrimary,
                            fontSize = 26.sp,
                            lineHeight = 30.sp,
                            fontWeight = FontWeight.Black,
                        )
                    }
                    Text(
                        "${filtered.size} 个",
                        color = tokens.textSecondary,
                        fontSize = 11.sp,
                    )
                }

                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    shape = RoundedCornerShape(20.dp),
                    leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                    placeholder = { Text("搜索字体") },
                )

                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 430.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    items(filtered, key = { it.id }) { font ->
                        Surface(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(24.dp))
                                .clickable { onChoose(font) },
                            shape = RoundedCornerShape(24.dp),
                            color = if (font.id == selected) {
                                MaterialTheme.colorScheme.primary.copy(alpha = .14f)
                            } else {
                                tokens.cardBackground
                            },
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 15.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Surface(
                                    modifier = Modifier.size(46.dp),
                                    shape = RoundedCornerShape(16.dp),
                                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                                ) {
                                    Box(contentAlignment = Alignment.Center) {
                                        Text(
                                            when (slot) {
                                                MixSlot.Cjk -> "中"
                                                MixSlot.Latin -> "Aa"
                                                MixSlot.Digit -> "123"
                                            },
                                            color = MaterialTheme.colorScheme.primary,
                                            fontWeight = FontWeight.Black,
                                            fontSize = if (slot == MixSlot.Digit) 11.sp else 16.sp,
                                        )
                                    }
                                }
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        font.name,
                                        color = tokens.textPrimary,
                                        fontWeight = FontWeight.Black,
                                        maxLines = 2,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                    Text(
                                        listOf(font.format, font.weightLabel).filter { it.isNotBlank() }.joinToString(" · "),
                                        color = tokens.textSecondary,
                                        fontSize = 10.sp,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                                if (font.id == selected) {
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

                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.End),
                ) {
                    Text("关闭", fontWeight = FontWeight.Bold)
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
