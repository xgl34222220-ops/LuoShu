package io.github.xgl34222220.luoshu.ui.library

import android.view.Gravity
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
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun FontLibraryScreenCompact(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    tools: @Composable () -> Unit,
) {
    val miuix = style == UiStyle.MIUIX
    val tokens = LocalMiuixTokens.current
    val cardColor = if (miuix) tokens.cardBackground else MaterialTheme.colorScheme.surfaceContainerLow
    val elevatedColor = if (miuix) tokens.elevatedCardBackground else MaterialTheme.colorScheme.surfaceContainerHigh
    val textPrimary = if (miuix) tokens.textPrimary else MaterialTheme.colorScheme.onSurface
    val textSecondary = if (miuix) tokens.textSecondary else MaterialTheme.colorScheme.onSurfaceVariant
    var showTools by rememberSaveable { mutableStateOf(false) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 10.dp, end = 16.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
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
                        fontSize = 34.sp,
                        lineHeight = 39.sp,
                        fontWeight = FontWeight.Black,
                    )
                    Text(
                        "${state.validCount}/${state.totalCount} 可用 · 当前显示 ${state.visibleCount}",
                        color = textSecondary,
                        fontSize = 12.sp,
                    )
                }
                Surface(
                    shape = RoundedCornerShape(17.dp),
                    color = elevatedColor,
                    tonalElevation = 2.dp,
                    shadowElevation = 3.dp,
                ) {
                    IconButton(
                        onClick = actions.refresh,
                        enabled = !state.loading,
                        modifier = Modifier.size(50.dp),
                    ) {
                        if (state.loading) {
                            CircularProgressIndicator(Modifier.size(21.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Rounded.Refresh, contentDescription = "刷新字体库")
                        }
                    }
                }
            }
        }

        item {
            OutlinedTextField(
                value = state.query,
                onValueChange = actions.setQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(20.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索名称、ID 或格式") },
            )
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
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
                    "排序：${state.sort.label}",
                    modifier = Modifier
                        .clickable {
                            val entries = FontLibrarySort.entries
                            val next = entries[(entries.indexOf(state.sort) + 1) % entries.size]
                            actions.setSort(next)
                        }
                        .padding(horizontal = 4.dp, vertical = 9.dp),
                    color = MaterialTheme.colorScheme.primary,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { showTools = !showTools }) {
                    Icon(
                        if (showTools) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                        contentDescription = null,
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(if (showTools) "收起导入与管理" else "导入与管理")
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
                        Text("调整搜索或筛选，也可以展开上方工具导入字体", color = textSecondary, fontSize = 11.sp)
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
        shape = RoundedCornerShape(23.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(50.dp),
                shape = RoundedCornerShape(17.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("系", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", color = textPrimary, fontSize = 16.sp, fontWeight = FontWeight.Black)
                Text("ROM 原始字体映射", color = textSecondary, fontSize = 11.sp)
            }
            if (active) {
                StatusPill("使用中", Color(0xFF21966C))
            } else {
                Button(onClick = onRestore, enabled = !busy, shape = RoundedCornerShape(16.dp)) {
                    Text("恢复")
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
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onDetails),
        shape = RoundedCornerShape(23.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) cardColor else MaterialTheme.colorScheme.errorContainer.copy(alpha = .42f),
        ),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(54.dp),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        if (font.valid) {
                            NativeFontPreview(
                                font = font,
                                text = "Aa",
                                axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                                modifier = Modifier.size(54.dp).padding(6.dp),
                                textSizeSp = 19f,
                                gravity = Gravity.CENTER,
                                maxLines = 1,
                            )
                        } else {
                            Text("Aa", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        font.name,
                        color = textPrimary,
                        fontSize = 17.sp,
                        lineHeight = 21.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = textSecondary,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        fontCapabilityLabel(font),
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (active) {
                    StatusPill("使用中", Color(0xFF21966C))
                } else {
                    IconButton(onClick = onDelete, enabled = !busy) {
                        Icon(Icons.Rounded.Delete, contentDescription = "删除字体", tint = textSecondary)
                    }
                }
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.Warning,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.error,
                        modifier = Modifier.size(16.dp),
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

            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "点击卡片查看完整预览与字体信息",
                    modifier = Modifier.weight(1f),
                    color = textSecondary,
                    fontSize = 11.sp,
                )
                if (!active) {
                    Button(
                        onClick = onApply,
                        enabled = font.valid && !busy,
                        shape = RoundedCornerShape(16.dp),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 9.dp),
                    ) {
                        Text("应用")
                    }
                } else {
                    Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = Color(0xFF21966C))
                }
            }
        }
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
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp),
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
