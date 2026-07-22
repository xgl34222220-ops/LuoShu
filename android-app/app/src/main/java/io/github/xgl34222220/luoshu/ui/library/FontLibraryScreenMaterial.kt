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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
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
        contentPadding = PaddingValues(start = 18.dp, top = 8.dp, end = 18.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item { MaterialLibraryHeader(state, actions.refresh) }
        item { topActions() }
        item { MaterialLibraryOverview(state) }
        item { MaterialBrowsePanel(state, actions) }

        if (state.loading || state.operationBusy) {
            item { LinearProgressIndicator(Modifier.fillMaxWidth().height(4.dp)) }
        }
        if (state.error.isNotBlank()) {
            item { MaterialLibraryMessage(state.error, error = true) }
        }
        if (state.operationMessage.isNotBlank()) {
            item { MaterialLibraryMessage(state.operationMessage, error = false, busy = state.operationBusy) }
        }

        item {
            MaterialSystemFontCard(
                active = state.activeFontId == "default",
                busy = state.operationBusy,
                onRestore = actions.restoreDefault,
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
        modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
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
            Text("字体库", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.Black)
            Text(
                "真实字体预览 · 共 ${state.totalCount} 个来源",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp,
            )
        }
        Surface(
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .84f),
            shadowElevation = 7.dp,
        ) {
            IconButton(onClick = onRefresh, modifier = Modifier.size(56.dp), enabled = !state.loading) {
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
private fun MaterialLibraryOverview(state: FontLibraryUiState) {
    val scheme = MaterialTheme.colorScheme
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        elevation = CardDefaults.cardElevation(defaultElevation = 8.dp),
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(scheme.primary, scheme.tertiary)))
                .drawBehind {
                    drawCircle(
                        brush = Brush.radialGradient(
                            colors = listOf(Color.White.copy(alpha = .32f), Color.Transparent),
                            center = Offset(size.width * .9f, 0f),
                            radius = size.width * .72f,
                        ),
                        center = Offset(size.width * .9f, 0f),
                        radius = size.width * .72f,
                    )
                }
                .padding(22.dp),
        ) {
            Column {
                Text("字体资源概览", color = Color.White.copy(alpha = .78f), fontSize = 12.sp)
                Spacer(Modifier.height(6.dp))
                Text(
                    "${state.validCount} 个可用字体",
                    color = Color.White,
                    fontSize = 28.sp,
                    lineHeight = 33.sp,
                    fontWeight = FontWeight.Black,
                )
                Spacer(Modifier.height(18.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
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
        shape = MaterialTheme.shapes.large,
        color = Color.White.copy(alpha = .16f),
        contentColor = Color.White,
    ) {
        Column(Modifier.padding(horizontal = 13.dp, vertical = 11.dp)) {
            Text(value, fontSize = 19.sp, fontWeight = FontWeight.Black)
            Text(label, color = Color.White.copy(alpha = .72f), fontSize = 10.sp)
        }
    }
}

@Composable
private fun MaterialBrowsePanel(state: FontLibraryUiState, actions: FontLibraryActions) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f),
        ),
    ) {
        Column(Modifier.padding(10.dp)) {
            OutlinedTextField(
                value = state.query,
                onValueChange = actions.setQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = MaterialTheme.shapes.large,
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索名称、ID 或格式") },
            )
            Spacer(Modifier.height(12.dp))
            Text("筛选", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, fontWeight = FontWeight.Bold)
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
            Text("排序", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, fontWeight = FontWeight.Bold)
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
private fun MaterialChoicePill(label: String, active: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = CircleShape,
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
private fun MaterialSystemFontCard(active: Boolean, busy: Boolean, onRestore: () -> Unit) {
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f),
        ),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(18.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                modifier = Modifier.size(52.dp),
                shape = MaterialTheme.shapes.large,
                color = MaterialTheme.colorScheme.primaryContainer,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("系", color = MaterialTheme.colorScheme.primary, fontSize = 20.sp, fontWeight = FontWeight.Black)
                }
            }
            Spacer(Modifier.width(13.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认字体", fontSize = 17.sp, fontWeight = FontWeight.Black)
                Text("恢复 ROM 原始字体映射", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
            }
            if (active) {
                MaterialLibraryPill("使用中", Color(0xFF21966C))
            } else {
                FilledTonalButton(onClick = onRestore, enabled = !busy) { Text("恢复") }
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
    val container = if (font.valid) {
        MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)
    } else {
        MaterialTheme.colorScheme.errorContainer.copy(alpha = .52f)
    }
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = container),
        elevation = CardDefaults.cardElevation(defaultElevation = if (active) 7.dp else 2.dp),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(52.dp).clickable(onClick = onDetails),
                    shape = MaterialTheme.shapes.large,
                    color = MaterialTheme.colorScheme.primaryContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontSize = 17.sp, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(13.dp))
                Column(Modifier.weight(1f).clickable(onClick = onDetails)) {
                    Text(
                        font.name,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) {
                    IconButton(onClick = onDelete, enabled = !busy) {
                        Icon(Icons.Rounded.Delete, contentDescription = "删除字体", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }

            Spacer(Modifier.height(14.dp))
            Surface(
                modifier = Modifier.fillMaxWidth().clickable(onClick = onDetails),
                shape = MaterialTheme.shapes.large,
                color = MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = .62f),
            ) {
                NativeFontPreview(
                    font = font,
                    text = fontPreviewText(font, detailed = true),
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier.fillMaxWidth().height(98.dp).padding(horizontal = 17.dp, vertical = 13.dp),
                    textSizeSp = 24f,
                    maxLines = 2,
                )
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(7.dp))
                    Text(font.error, color = MaterialTheme.colorScheme.error, fontSize = 10.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }

            Spacer(Modifier.height(12.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f))
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                MaterialLibraryPill(fontCapabilityLabel(font), MaterialTheme.colorScheme.primary)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onDetails) { Text("详情") }
                if (active) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(5.dp))
                        Text("当前使用", color = MaterialTheme.colorScheme.primary, fontSize = 12.sp, fontWeight = FontWeight.Black)
                    }
                } else {
                    Button(onClick = onApply, enabled = font.valid && !busy) {
                        Text("应用字体", fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}

@Composable
private fun MaterialLibraryMessage(message: String, error: Boolean, busy: Boolean = false) {
    Surface(
        shape = MaterialTheme.shapes.large,
        color = if (error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.secondaryContainer,
    ) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
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
                color = if (error) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSecondaryContainer,
                fontSize = 12.sp,
            )
        }
    }
}

@Composable
private fun MaterialLibraryEmpty(state: FontLibraryUiState) {
    val filtered = state.filter != FontLibraryFilter.ALL
    Card(
        shape = MaterialTheme.shapes.extraLarge,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow.copy(alpha = .84f)),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(34.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(Icons.Rounded.FontDownload, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(42.dp))
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
                    else -> "使用右下角导入按钮选择 TTF、OTF、TTC 或模块 ZIP"
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
        )
    }
}