package io.github.xgl34222220.luoshu.ui.library

import android.view.Gravity
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlyph
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuIconTokens

@Composable
internal fun FontLibraryScreenCompact(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    tools: @Composable () -> Unit,
) {
    val miuix = style == UiStyle.MIUIX
    val dockBottomPadding = maxOf(LocalDockContentPadding.current, 28.dp)
    val tokens = LocalMiuixTokens.current
    val cardColor = if (miuix) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow
    val elevatedColor = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh
    val textPrimary = if (miuix) tokens.textPrimary else MaterialTheme.colorScheme.onSurface
    val textSecondary = if (miuix) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    var showTools by rememberSaveable { mutableStateOf(false) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 14.dp, top = 8.dp, end = 14.dp, bottom = dockBottomPadding),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(
                        "FONT LIBRARY",
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.2.sp,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "字体库",
                        color = textPrimary,
                        fontSize = 29.sp,
                        lineHeight = 33.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        "${state.visibleCount} 款字体 · ${state.validCount} 款可用",
                        color = textSecondary,
                        fontSize = 11.sp,
                    )
                }
                LuoShuHeaderAction(
                    icon = Icons.Rounded.Refresh,
                    contentDescription = "刷新字体库",
                    onClick = actions.refresh,
                    enabled = !state.loading,
                    loading = state.loading,
                    containerColor = elevatedColor,
                )
            }
        }

        item {
            TextField(
                value = state.query,
                onValueChange = actions.setQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(18.dp),
                leadingIcon = {
                    LuoShuGlyph(
                        imageVector = Icons.Rounded.Search,
                        contentDescription = null,
                        size = LuoShuIconTokens.SectionGlyph,
                    )
                },
                placeholder = { Text("搜索字体") },
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = elevatedColor,
                    unfocusedContainerColor = elevatedColor,
                    disabledContainerColor = elevatedColor,
                    focusedIndicatorColor = Color.Transparent,
                    unfocusedIndicatorColor = Color.Transparent,
                    disabledIndicatorColor = Color.Transparent,
                ),
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                FontLibraryFilter.entries.forEach { option ->
                    ChoicePill(
                        label = option.label,
                        active = state.filter == option,
                        onClick = { actions.setFilter(option) },
                    )
                }
            }
        }

        item {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "共 ${state.visibleCount} 款",
                    color = textSecondary,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Medium,
                )
                Spacer(Modifier.weight(1f))
                Surface(
                    modifier = Modifier.clickable {
                        val entries = FontLibrarySort.entries
                        val next = entries[(entries.indexOf(state.sort) + 1) % entries.size]
                        actions.setSort(next)
                    },
                    shape = RoundedCornerShape(999.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerHigh,
                ) {
                    Text(
                        "排序 · ${state.sort.label}",
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Spacer(Modifier.width(6.dp))
                TextButton(onClick = { showTools = !showTools }) {
                    LuoShuGlyph(
                        imageVector = if (showTools) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                        contentDescription = null,
                        size = LuoShuIconTokens.SectionGlyph,
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(if (showTools) "收起管理" else "管理")
                }
            }
        }

        if (showTools) {
            item { tools() }
        }

        if (state.loading || state.operationBusy) {
            item {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth().height(4.dp),
                )
            }
        }

        if (state.error.isNotBlank()) {
            item { NoticeCard(state.error, error = true) }
        }
        if (state.operationMessage.isNotBlank()) {
            item { NoticeCard(state.operationMessage, error = false) }
        }

        item {
            CompactSystemFontRow(
                active = state.activeFontId == "default",
                busy = state.operationBusy,
                cardColor = cardColor,
                textPrimary = textPrimary,
                textSecondary = textSecondary,
                onRestore = actions.restoreDefault,
            )
        }

        if (!state.loading && state.fonts.isEmpty()) {
            item {
                Card(
                    shape = RoundedCornerShape(24.dp),
                    colors = CardDefaults.cardColors(containerColor = cardColor),
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(28.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Icon(
                            Icons.Rounded.FontDownload,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.size(40.dp),
                        )
                        Spacer(Modifier.height(10.dp))
                        Text("没有符合条件的字体", color = textPrimary, fontSize = 18.sp, fontWeight = FontWeight.Black)
                        Text("调整搜索或筛选，也可以展开管理工具导入字体", color = textSecondary, fontSize = 11.sp)
                    }
                }
            }
        }

        items(state.fonts, key = { it.id }) { font ->
            CompactFontRow(
                font = font,
                active = state.activeFontId == font.id,
                busy = state.operationBusy,
                cardColor = cardColor,
                textPrimary = textPrimary,
                textSecondary = textSecondary,
                onDetails = { actions.details(font) },
                onApply = { actions.apply(font) },
                onDelete = { actions.delete(font) },
            )
        }
    }
}

@Composable
private fun CompactSystemFontRow(
    active: Boolean,
    busy: Boolean,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
    onRestore: () -> Unit,
) {
    Card(
        shape = RoundedCornerShape(19.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
        border = if (active) BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .24f)) else null,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(50.dp),
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        "Aa12",
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Black,
                    )
                }
            }
            Spacer(Modifier.width(13.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", color = textPrimary, fontSize = 15.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.height(2.dp))
                Text("ROM 原始字体映射", color = textSecondary, fontSize = 10.sp)
                Spacer(Modifier.height(7.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FontLibraryBadge("系统")
                    FontLibraryBadge("默认")
                }
            }
            Spacer(Modifier.width(10.dp))
            if (active) {
                StatusPill("使用中", Color(0xFF21966C))
            } else {
                FilledTonalButton(
                    onClick = onRestore,
                    enabled = !busy,
                    shape = RoundedCornerShape(14.dp),
                    contentPadding = PaddingValues(horizontal = 15.dp, vertical = 8.dp),
                ) {
                    Text("恢复", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun CompactFontRow(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    cardColor: Color,
    textPrimary: Color,
    textSecondary: Color,
    onDetails: () -> Unit,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    var menuExpanded by remember(font.id) { mutableStateOf(false) }
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onDetails),
        shape = RoundedCornerShape(19.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) cardColor else MaterialTheme.colorScheme.errorContainer.copy(alpha = .34f),
        ),
        border = if (active) BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = .24f)) else null,
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(50.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = if (font.valid) {
                        MaterialTheme.colorScheme.primary.copy(alpha = .09f)
                    } else {
                        MaterialTheme.colorScheme.error.copy(alpha = .08f)
                    },
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        if (font.valid) {
                            NativeFontPreview(
                                font = font,
                                text = "Aa12",
                                axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                                modifier = Modifier.size(50.dp).padding(5.dp),
                                textSizeSp = 14f,
                                gravity = Gravity.CENTER,
                                maxLines = 1,
                            )
                        } else {
                            Text(
                                "Aa12",
                                color = MaterialTheme.colorScheme.error,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Black,
                            )
                        }
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        font.name,
                        color = textPrimary,
                        fontSize = 15.sp,
                        lineHeight = 19.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = textSecondary,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(7.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FontLibraryBadge(fontPrimaryBadge(font))
                        FontLibraryBadge(if (font.supportsCjk) "中日韩" else "拉丁")
                    }
                }
                Spacer(Modifier.width(4.dp))
                Box {
                    IconButton(onClick = { menuExpanded = true }, enabled = !busy && !active) {
                        LuoShuGlyph(
                            imageVector = Icons.Rounded.MoreVert,
                            contentDescription = "更多字体操作",
                            size = LuoShuIconTokens.ToolGlyph,
                            opticalScale = .92f,
                            tint = if (active) textSecondary.copy(alpha = .38f) else textSecondary,
                        )
                    }
                    DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                        DropdownMenuItem(
                            text = { Text("删除字体") },
                            leadingIcon = {
                                LuoShuGlyph(
                                    imageVector = Icons.Rounded.Delete,
                                    contentDescription = null,
                                    size = LuoShuIconTokens.ToolGlyph,
                                    opticalScale = .96f,
                                )
                            },
                            enabled = !busy,
                            onClick = {
                                menuExpanded = false
                                onDelete()
                            },
                        )
                    }
                }
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    LuoShuGlyph(
                        imageVector = Icons.Rounded.Warning,
                        contentDescription = null,
                        size = LuoShuIconTokens.SectionGlyph,
                        opticalScale = .96f,
                        tint = MaterialTheme.colorScheme.error,
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        font.error,
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 11.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }

            Spacer(Modifier.height(11.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    if (font.valid) "轻触卡片预览" else "字体需要检查",
                    modifier = Modifier.weight(1f),
                    color = textSecondary.copy(alpha = .82f),
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Medium,
                )
                if (active) {
                    StatusPill("使用中", Color(0xFF21966C))
                } else {
                    Button(
                        onClick = onApply,
                        enabled = font.valid && !busy,
                        modifier = Modifier.height(38.dp),
                        shape = RoundedCornerShape(14.dp),
                        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 0.dp),
                    ) {
                        Text("应用", fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

private fun fontPrimaryBadge(font: FontItem): String = when {
    font.variable -> "可变字体"
    font.weights.size > 1 -> "${font.weights.size} 字重"
    else -> "单字重"
}

@Composable
private fun FontLibraryBadge(text: String) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = .58f),
    ) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            color = MaterialTheme.colorScheme.onPrimaryContainer,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
    }
}

@Composable
private fun ChoicePill(label: String, active: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
            color = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
    }
}

@Composable
private fun NoticeCard(message: String, error: Boolean) {
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = if (error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.primaryContainer,
    ) {
        Text(
            message,
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            color = if (error) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onPrimaryContainer,
            fontSize = 12.sp,
        )
    }
}

@Composable
private fun StatusPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .12f)) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
        )
    }
}
