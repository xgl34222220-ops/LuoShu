package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import io.github.xgl34222220.luoshu.ui.font.fontPreviewText
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun FontLibraryScreenMiuix(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MiuixLibraryHeader(state, actions.refresh) }
        item { topActions() }
        item { MiuixBrowsePanel(state, actions) }

        if (state.loading || state.operationBusy) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth().height(4.dp)) }
        }
        if (state.error.isNotBlank()) {
            item { MiuixLibraryNotice(state.error, error = true) }
        }
        if (state.operationMessage.isNotBlank()) {
            item { MiuixLibraryNotice(state.operationMessage, error = false, busy = state.operationBusy) }
        }

        item {
            MiuixSectionLabel(
                title = "系统字体",
                subtitle = if (state.activeFontId == "default") "当前使用 ROM 原始字体" else "可随时恢复原始映射",
            )
        }
        item {
            MiuixSystemFontRow(
                active = state.activeFontId == "default",
                busy = state.operationBusy,
                onRestore = actions.restoreDefault,
            )
        }

        item {
            MiuixSectionLabel(
                title = "已导入字体",
                subtitle = "显示 ${state.visibleCount} 个 · ${state.sort.label}",
            )
        }
        if (!state.loading && state.fonts.isEmpty()) {
            item { MiuixLibraryEmpty(state) }
        }
        items(state.fonts, key = { it.id }) { font ->
            MiuixFontCard(
                font = font,
                active = state.activeFontId == font.id,
                busy = state.operationBusy,
                onDetails = { actions.details(font) },
                onApply = { actions.apply(font) },
                onDelete = { actions.delete(font) },
            )
        }
    }
}

@Composable
private fun MiuixLibraryHeader(state: FontLibraryUiState, onRefresh: () -> Unit) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                "FONT LIBRARY",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.4.sp,
            )
            Spacer(Modifier.height(3.dp))
            Text(
                "字体库",
                color = tokens.textPrimary,
                fontSize = 38.sp,
                lineHeight = 43.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                "${state.validCount}/${state.totalCount} 可用 · ${state.variableCount} 个可变字体",
                color = tokens.textSecondary,
                fontSize = 12.sp,
            )
        }
        Card(
            shape = RoundedCornerShape(18.dp),
            colors = CardDefaults.cardColors(containerColor = tokens.elevatedCardBackground),
            elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
        ) {
            IconButton(onClick = onRefresh, enabled = !state.loading, modifier = Modifier.size(56.dp)) {
                if (state.loading) {
                    CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Rounded.Refresh, contentDescription = "刷新字体库")
                }
            }
        }
    }
}

@Composable
private fun MiuixBrowsePanel(state: FontLibraryUiState, actions: FontLibraryActions) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(30.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            OutlinedTextField(
                value = state.query,
                onValueChange = actions.setQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(22.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索名称、ID 或格式") },
            )
            Spacer(Modifier.height(12.dp))
            Text("筛选", color = tokens.textSecondary, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(7.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FontLibraryFilter.entries.forEach { option ->
                    MiuixChoicePill(
                        label = option.label,
                        active = state.filter == option,
                        onClick = { actions.setFilter(option) },
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            Text("排序", color = tokens.textSecondary, fontSize = 10.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(7.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FontLibrarySort.entries.forEach { option ->
                    MiuixChoicePill(
                        label = option.label,
                        active = state.sort == option,
                        onClick = { actions.setSort(option) },
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MiuixMetricPill("结果", state.visibleCount, Modifier.weight(1f))
                MiuixMetricPill("可变", state.variableCount, Modifier.weight(1f))
                MiuixMetricPill("多字重", state.multiWeightCount, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MiuixChoicePill(label: String, active: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(999.dp),
        color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp),
            color = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun MiuixMetricPill(label: String, value: Int, modifier: Modifier) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.primary.copy(alpha = .09f),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(value.toString(), color = MaterialTheme.colorScheme.primary, fontSize = 17.sp, fontWeight = FontWeight.Black)
            Spacer(Modifier.width(6.dp))
            Text(label, color = tokens.textSecondary, fontSize = 10.sp)
        }
    }
}

@Composable
private fun MiuixSectionLabel(title: String, subtitle: String) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(title, color = tokens.textPrimary, fontSize = 22.sp, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f))
        Text(subtitle, color = tokens.textSecondary, fontSize = 10.sp)
    }
}

@Composable
private fun MiuixSystemFontRow(active: Boolean, busy: Boolean, onRestore: () -> Unit) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 3.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(17.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(50.dp),
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("系", color = MaterialTheme.colorScheme.primary, fontSize = 20.sp, fontWeight = FontWeight.Black)
                }
            }
            Spacer(Modifier.width(13.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", color = tokens.textPrimary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                Text("ROM 原始字体映射", color = tokens.textSecondary, fontSize = 11.sp)
            }
            if (active) {
                MiuixLibraryPill("使用中", tokens.success)
            } else {
                Button(onClick = onRestore, enabled = !busy, shape = RoundedCornerShape(17.dp)) {
                    Text("恢复", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun MiuixFontCard(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    onDetails: () -> Unit,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val shape = RoundedCornerShape(28.dp)
    Card(
        modifier = Modifier.fillMaxWidth().shadow(if (active) 8.dp else 3.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) tokens.cardBackground else MaterialTheme.colorScheme.errorContainer.copy(alpha = .42f),
        ),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp).clickable(onClick = onDetails),
                    shape = RoundedCornerShape(18.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .heightIn(min = 52.dp)
                        .clickable(onClick = onDetails),
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        font.name,
                        color = tokens.textPrimary,
                        fontSize = 18.sp,
                        lineHeight = 22.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = tokens.textSecondary,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) {
                    Spacer(Modifier.width(6.dp))
                    Surface(
                        onClick = onDelete,
                        enabled = !busy,
                        modifier = Modifier.size(40.dp),
                        shape = RoundedCornerShape(14.dp),
                        color = tokens.textPrimary.copy(alpha = .055f),
                        contentColor = tokens.textSecondary,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                Icons.Rounded.Delete,
                                contentDescription = "删除字体",
                                modifier = Modifier.size(20.dp),
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.height(13.dp))
            Surface(
                modifier = Modifier.fillMaxWidth().clickable(onClick = onDetails),
                shape = RoundedCornerShape(22.dp),
                color = tokens.textPrimary.copy(alpha = .035f),
            ) {
                NativeFontPreview(
                    font = font,
                    text = fontPreviewText(font),
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier.fillMaxWidth().height(88.dp).padding(horizontal = 15.dp, vertical = 14.dp),
                    textSizeSp = 22f,
                    maxLines = 1,
                )
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
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
                        fontSize = 10.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }

            Spacer(Modifier.height(12.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .34f))
            Spacer(Modifier.height(11.dp))
            MiuixCapabilityStrip(fontCapabilityLabel(font))
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                MiuixCardAction(
                    label = "查看详情",
                    primary = false,
                    enabled = true,
                    onClick = onDetails,
                    modifier = Modifier.weight(1f),
                )
                if (active) {
                    MiuixCurrentAction(modifier = Modifier.weight(1f), color = tokens.success)
                } else {
                    MiuixCardAction(
                        label = "应用字体",
                        primary = true,
                        enabled = font.valid && !busy,
                        onClick = onApply,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

@Composable
private fun MiuixCapabilityStrip(text: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.primary.copy(alpha = .075f),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
            color = MaterialTheme.colorScheme.primary,
            fontSize = 10.sp,
            lineHeight = 14.sp,
            fontWeight = FontWeight.Black,
            maxLines = 1,
            softWrap = false,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun MiuixCardAction(
    label: String,
    primary: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val container = when {
        primary && enabled -> scheme.primary
        primary -> scheme.surfaceVariant
        else -> scheme.surfaceContainerHigh
    }
    val content = when {
        primary && enabled -> scheme.onPrimary
        primary -> scheme.onSurfaceVariant
        else -> scheme.onSurface
    }
    Surface(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.defaultMinSize(minHeight = 44.dp),
        shape = RoundedCornerShape(16.dp),
        color = container,
        contentColor = content,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                label,
                color = content,
                fontSize = 12.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                softWrap = false,
            )
            if (primary) {
                Spacer(Modifier.width(4.dp))
                Icon(
                    Icons.Rounded.ChevronRight,
                    contentDescription = null,
                    modifier = Modifier.size(17.dp),
                    tint = content,
                )
            }
        }
    }
}

@Composable
private fun MiuixCurrentAction(modifier: Modifier = Modifier, color: Color) {
    Surface(
        modifier = modifier.defaultMinSize(minHeight = 44.dp),
        shape = RoundedCornerShape(16.dp),
        color = color.copy(alpha = .11f),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = color, modifier = Modifier.size(17.dp))
            Spacer(Modifier.width(6.dp))
            Text(
                "正在使用",
                color = color,
                fontSize = 12.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1,
                softWrap = false,
            )
        }
    }
}

@Composable
private fun MiuixLibraryNotice(message: String, error: Boolean, busy: Boolean = false) {
    val tokens = LocalMiuixTokens.current
    Surface(
        shape = RoundedCornerShape(27.dp),
        color = if (error) MaterialTheme.colorScheme.errorContainer else tokens.cardBackground,
        shadowElevation = if (error) 0.dp else 4.dp,
    ) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp)
            } else {
                Icon(
                    if (error) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    tint = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                )
            }
            Spacer(Modifier.width(10.dp))
            Text(
                message,
                modifier = Modifier.weight(1f),
                color = if (error) MaterialTheme.colorScheme.onErrorContainer else tokens.textPrimary,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun MiuixLibraryEmpty(state: FontLibraryUiState) {
    val tokens = LocalMiuixTokens.current
    val filtered = state.filter != FontLibraryFilter.ALL
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(34.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Surface(
                modifier = Modifier.size(58.dp),
                shape = RoundedCornerShape(21.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Rounded.FontDownload, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(13.dp))
            Text(
                when {
                    state.query.isNotBlank() -> "没有匹配的字体"
                    filtered -> "当前筛选没有结果"
                    else -> "还没有导入字体"
                },
                color = tokens.textPrimary,
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                when {
                    state.query.isNotBlank() -> "清空搜索或尝试其他关键词"
                    filtered -> "切换到“全部”查看其他字体"
                    else -> "点击右下角导入按钮添加字体文件"
                },
                color = tokens.textSecondary,
                fontSize = 11.sp,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Composable
private fun MiuixLibraryPill(text: String, color: Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .12f)) {
        Text(
            text,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
            color = color,
            fontSize = 10.sp,
            fontWeight = FontWeight.Black,
            maxLines = 1,
            softWrap = false,
            overflow = TextOverflow.Ellipsis,
        )
    }
}
