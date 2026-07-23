package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
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
import androidx.compose.runtime.Composable
import android.view.Gravity
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
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

@Composable
internal fun FontLibraryScreenMaterial(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 10.dp, end = 16.dp, bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialLibraryHeader(state, actions.refresh) }
        item { topActions() }
        item { MaterialLibraryOverview(state) }
        item { MaterialBrowsePanel(state, actions) }

        if (state.loading || state.operationBusy) {
            item {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth().height(4.dp),
                    trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
                )
            }
        }
        if (state.error.isNotBlank()) {
            item { MaterialLibraryMessage(state.error, error = true) }
        }
        if (state.operationMessage.isNotBlank()) {
            item {
                MaterialLibraryMessage(
                    message = state.operationMessage,
                    error = false,
                    busy = state.operationBusy,
                )
            }
        }

        item {
            MaterialSectionLabel(
                title = "系统字体",
                subtitle = if (state.activeFontId == "default") "正在使用 ROM 原始映射" else "可随时恢复系统字体",
            )
        }
        item {
            MaterialSystemFontCard(
                active = state.activeFontId == "default",
                busy = state.operationBusy,
                onRestore = actions.restoreDefault,
            )
        }

        item {
            MaterialSectionLabel(
                title = "已导入字体",
                subtitle = "显示 ${state.visibleCount} 个 · ${state.sort.label}",
            )
        }
        if (!state.loading && state.fonts.isEmpty()) {
            item { MaterialLibraryEmpty(state) }
        }
        items(state.fonts, key = { it.id }) { font ->
            MaterialFontCard(
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
private fun MaterialLibraryHeader(state: FontLibraryUiState, onRefresh: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(top = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                "FONT LIBRARY",
                color = MaterialTheme.colorScheme.primary,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 2.2.sp,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "字体库",
                color = MaterialTheme.colorScheme.onBackground,
                fontSize = 34.sp,
                lineHeight = 39.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                "管理与应用本地字体 · ${state.validCount}/${state.totalCount} 可用",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
        Surface(
            shape = RoundedCornerShape(18.dp),
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
            shadowElevation = 4.dp,
        ) {
            IconButton(
                onClick = onRefresh,
                modifier = Modifier.size(52.dp),
                enabled = !state.loading,
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

@Composable
private fun MaterialLibraryOverview(state: FontLibraryUiState) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(28.dp)
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = shape,
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        elevation = CardDefaults.cardElevation(defaultElevation = 5.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(scheme.primary, scheme.tertiary)))
                .drawBehind {
                    drawCircle(
                        brush = Brush.radialGradient(
                            colors = listOf(Color.White.copy(alpha = .30f), Color.Transparent),
                            center = Offset(size.width * .92f, size.height * .08f),
                            radius = size.width * .70f,
                        ),
                        center = Offset(size.width * .92f, size.height * .08f),
                        radius = size.width * .70f,
                    )
                }
                .padding(horizontal = 20.dp, vertical = 18.dp),
        ) {
            Column {
                Text(
                    "字体资源概览",
                    color = Color.White.copy(alpha = .78f),
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "${state.validCount} 个可用字体",
                    color = Color.White,
                    fontSize = 25.sp,
                    lineHeight = 30.sp,
                    fontWeight = FontWeight.Black,
                )
                Spacer(Modifier.height(15.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    MaterialOverviewMetric("结果", state.visibleCount.toString(), Modifier.weight(1f))
                    MaterialOverviewMetric("可变", state.variableCount.toString(), Modifier.weight(1f))
                    MaterialOverviewMetric("多字重", state.multiWeightCount.toString(), Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun MaterialOverviewMetric(label: String, value: String, modifier: Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = Color.White.copy(alpha = .16f),
        contentColor = Color.White,
    ) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
            Text(value, fontSize = 18.sp, fontWeight = FontWeight.Black)
            Text(label, color = Color.White.copy(alpha = .72f), fontSize = 10.sp)
        }
    }
}

@Composable
private fun MaterialBrowsePanel(state: FontLibraryUiState, actions: FontLibraryActions) {
    Card(
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            OutlinedTextField(
                value = state.query,
                onValueChange = actions.setQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(20.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索名称、ID 或格式") },
            )
            Spacer(Modifier.height(12.dp))
            MaterialPanelLabel("筛选")
            Spacer(Modifier.height(7.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FontLibraryFilter.entries.forEach { option ->
                    MaterialChoicePill(
                        label = option.label,
                        active = state.filter == option,
                        onClick = { actions.setFilter(option) },
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            MaterialPanelLabel("排序")
            Spacer(Modifier.height(7.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FontLibrarySort.entries.forEach { option ->
                    MaterialChoicePill(
                        label = option.label,
                        active = state.sort == option,
                        onClick = { actions.setSort(option) },
                    )
                }
            }
        }
    }
}

@Composable
private fun MaterialPanelLabel(text: String) {
    Text(
        text,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        fontSize = 10.sp,
        fontWeight = FontWeight.Bold,
        letterSpacing = .5.sp,
    )
}

@Composable
private fun MaterialChoicePill(label: String, active: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = CircleShape,
        color = if (active) {
            MaterialTheme.colorScheme.primary
        } else {
            MaterialTheme.colorScheme.surfaceContainerHigh
        },
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp),
            color = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            softWrap = false,
        )
    }
}

@Composable
private fun MaterialSectionLabel(title: String, subtitle: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        Text(
            title,
            modifier = Modifier.weight(1f),
            color = MaterialTheme.colorScheme.onBackground,
            fontSize = 21.sp,
            fontWeight = FontWeight.Black,
        )
        Text(
            subtitle,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 10.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun MaterialSystemFontCard(active: Boolean, busy: Boolean, onRestore: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(26.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(54.dp),
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        "系",
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Black,
                    )
                }
            }
            Spacer(Modifier.width(13.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "系统默认字体",
                    color = MaterialTheme.colorScheme.onSurface,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Black,
                )
                Text(
                    "恢复 ROM 原始字体映射",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                )
            }
            Spacer(Modifier.width(8.dp))
            if (active) {
                MaterialLibraryPill("使用中", Color(0xFF21966C))
            } else {
                MaterialCardAction(
                    label = "恢复",
                    primary = false,
                    enabled = !busy,
                    onClick = onRestore,
                    modifier = Modifier.width(82.dp),
                    showArrow = false,
                )
            }
        }
    }
}

@Composable
private fun MaterialFontCard(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    onDetails: () -> Unit,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    val scheme = MaterialTheme.colorScheme
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) {
                scheme.surfaceContainerLow
            } else {
                scheme.errorContainer.copy(alpha = .55f)
            },
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = if (active) 5.dp else 2.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(56.dp).clickable(onClick = onDetails),
                    shape = RoundedCornerShape(19.dp),
                    color = scheme.primaryContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        if (font.valid) {
                            NativeFontPreview(
                                font = font,
                                text = "Aa",
                                axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                                modifier = Modifier.size(56.dp).padding(7.dp),
                                textSizeSp = 19f,
                                gravity = Gravity.CENTER,
                                maxLines = 1,
                            )
                        } else {
                            Text(
                                "Aa",
                                color = scheme.primary,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Black,
                            )
                        }
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .heightIn(min = 56.dp)
                        .clickable(onClick = onDetails),
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        font.name,
                        color = scheme.onSurface,
                        fontSize = 18.sp,
                        lineHeight = 22.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        listOf(font.format, font.size, font.date)
                            .filter { it.isNotBlank() }
                            .joinToString(" · "),
                        color = scheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Spacer(Modifier.width(6.dp))
                if (active) {
                    MaterialLibraryPill("使用中", Color(0xFF21966C))
                } else {
                    Surface(
                        onClick = onDelete,
                        enabled = !busy,
                        modifier = Modifier.size(40.dp),
                        shape = CircleShape,
                        color = scheme.surfaceContainerHigh,
                        contentColor = scheme.onSurfaceVariant,
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

            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier.fillMaxWidth().clickable(onClick = onDetails),
                shape = RoundedCornerShape(22.dp),
                color = scheme.surfaceContainerHighest.copy(alpha = .60f),
            ) {
                NativeFontPreview(
                    font = font,
                    text = fontPreviewText(font, detailed = true),
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(102.dp)
                        .padding(horizontal = 16.dp, vertical = 14.dp),
                    textSizeSp = 23f,
                    maxLines = 2,
                )
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Rounded.Warning,
                        contentDescription = null,
                        tint = scheme.error,
                        modifier = Modifier.size(17.dp),
                    )
                    Spacer(Modifier.width(7.dp))
                    Text(
                        font.error,
                        color = scheme.error,
                        fontSize = 10.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }

            Spacer(Modifier.height(12.dp))
            HorizontalDivider(color = scheme.outlineVariant.copy(alpha = .44f))
            Spacer(Modifier.height(11.dp))
            MaterialCapabilityStrip(fontCapabilityLabel(font))
            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                MaterialCardAction(
                    label = "查看详情",
                    primary = false,
                    enabled = true,
                    onClick = onDetails,
                    modifier = Modifier.weight(1f),
                    showArrow = false,
                )
                if (active) {
                    MaterialCurrentAction(
                        modifier = Modifier.weight(1f),
                        color = Color(0xFF21966C),
                    )
                } else {
                    MaterialCardAction(
                        label = "应用字体",
                        primary = true,
                        enabled = font.valid && !busy,
                        onClick = onApply,
                        modifier = Modifier.weight(1f),
                        showArrow = true,
                    )
                }
            }
        }
    }
}

@Composable
private fun MaterialCapabilityStrip(text: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.primary.copy(alpha = .085f),
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
private fun MaterialCardAction(
    label: String,
    primary: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    showArrow: Boolean,
) {
    val scheme = MaterialTheme.colorScheme
    val container = when {
        primary && enabled -> scheme.primary
        primary -> scheme.surfaceVariant
        else -> scheme.surfaceContainerHigh
    }
    val content = when {
        primary && enabled -> scheme.onPrimary
        primary -> scheme.onSurfaceVariant.copy(alpha = .68f)
        else -> scheme.onSurface
    }
    Surface(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.defaultMinSize(minHeight = 46.dp),
        shape = RoundedCornerShape(16.dp),
        color = container,
        contentColor = content,
        shadowElevation = if (primary && enabled) 2.dp else 0.dp,
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
            if (showArrow) {
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
private fun MaterialCurrentAction(modifier: Modifier = Modifier, color: Color) {
    Surface(
        modifier = modifier.defaultMinSize(minHeight = 46.dp),
        shape = RoundedCornerShape(16.dp),
        color = color.copy(alpha = .12f),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Rounded.CheckCircle,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(17.dp),
            )
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
private fun MaterialLibraryMessage(message: String, error: Boolean, busy: Boolean = false) {
    Surface(
        shape = RoundedCornerShape(22.dp),
        color = if (error) {
            MaterialTheme.colorScheme.errorContainer
        } else {
            MaterialTheme.colorScheme.secondaryContainer
        },
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp)
            } else {
                Icon(
                    if (error) Icons.Rounded.Warning else Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    tint = if (error) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.secondary,
                )
            }
            Spacer(Modifier.width(10.dp))
            Text(
                message,
                modifier = Modifier.weight(1f),
                color = if (error) {
                    MaterialTheme.colorScheme.onErrorContainer
                } else {
                    MaterialTheme.colorScheme.onSecondaryContainer
                },
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun MaterialLibraryEmpty(state: FontLibraryUiState) {
    val filtered = state.filter != FontLibraryFilter.ALL
    Card(
        shape = RoundedCornerShape(30.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(34.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Surface(
                modifier = Modifier.size(58.dp),
                shape = RoundedCornerShape(20.dp),
                color = MaterialTheme.colorScheme.primaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Rounded.FontDownload,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            Spacer(Modifier.height(13.dp))
            Text(
                when {
                    state.query.isNotBlank() -> "没有匹配的字体"
                    filtered -> "当前筛选没有结果"
                    else -> "还没有导入字体"
                },
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                when {
                    state.query.isNotBlank() -> "换一个关键词，或者清空搜索条件"
                    filtered -> "切换到“全部”查看其他字体"
                    else -> "使用页面上方的导入工具栏添加 TTF、OTF、TTC 或模块 ZIP"
                },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 11.sp,
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Composable
private fun MaterialLibraryPill(text: String, color: Color) {
    Surface(shape = CircleShape, color = color.copy(alpha = .12f)) {
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
