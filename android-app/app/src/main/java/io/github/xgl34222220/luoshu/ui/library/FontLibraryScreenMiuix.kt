package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens

@Composable
internal fun FontLibraryScreenMiuix(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 132.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MiuixLibraryHeader(state, actions.refresh) }
        item { MiuixSearchPanel(state, actions.setQuery) }

        if (state.loading || state.operationBusy) {
            item {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth().height(4.dp),
                )
            }
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
                subtitle = "${state.fonts.size} 个结果 · ${state.variableCount} 个可变字体",
            )
        }

        if (!state.loading && state.fonts.isEmpty()) {
            item { MiuixLibraryEmpty(state.query) }
        }

        items(state.fonts, key = { it.id }) { font ->
            MiuixFontCard(
                font = font,
                active = state.activeFontId == font.id,
                busy = state.operationBusy,
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
        modifier = Modifier.fillMaxWidth().statusBarsPadding().padding(top = 4.dp),
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
                fontSize = 42.sp,
                lineHeight = 47.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                "${state.validCount}/${state.totalCount} 可用 · ${state.multiWeightCount} 个多字重来源",
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
private fun MiuixSearchPanel(state: FontLibraryUiState, onQuery: (String) -> Unit) {
    val tokens = LocalMiuixTokens.current
    Card(
        shape = RoundedCornerShape(34.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 7.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            OutlinedTextField(
                value = state.query,
                onValueChange = onQuery,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                shape = RoundedCornerShape(22.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                placeholder = { Text("搜索字体名称或格式") },
            )
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MiuixMetricPill("全部", state.totalCount, Modifier.weight(1f))
                MiuixMetricPill("可变", state.variableCount, Modifier.weight(1f))
                MiuixMetricPill("多字重", state.multiWeightCount, Modifier.weight(1f))
            }
        }
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
        shape = RoundedCornerShape(32.dp),
        colors = CardDefaults.cardColors(containerColor = tokens.cardBackground),
        elevation = CardDefaults.cardElevation(defaultElevation = 6.dp),
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
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val shape = RoundedCornerShape(34.dp)
    Card(
        modifier = Modifier.fillMaxWidth().shadow(if (active) 10.dp else 6.dp, shape, clip = false),
        shape = shape,
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) tokens.cardBackground else MaterialTheme.colorScheme.errorContainer.copy(alpha = .48f),
        ),
    ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 15.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(48.dp),
                    shape = RoundedCornerShape(17.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = .11f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontSize = 16.sp, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        font.name,
                        color = tokens.textPrimary,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        listOf(font.format, font.size).filter { it.isNotBlank() }.joinToString(" · "),
                        color = tokens.textSecondary,
                        fontSize = 10.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (!active) {
                    IconButton(onClick = onDelete, enabled = !busy) {
                        Icon(Icons.Rounded.Delete, contentDescription = "删除字体", tint = tokens.textSecondary)
                    }
                }
            }

            Spacer(Modifier.height(12.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(24.dp),
                color = tokens.textPrimary.copy(alpha = .038f),
            ) {
                NativeFontPreview(
                    font = font,
                    text = "洛书字体预览  Hello 0123456789",
                    axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                    modifier = Modifier.fillMaxWidth().height(80.dp).padding(horizontal = 16.dp, vertical = 12.dp),
                    textSizeSp = 23f,
                    maxLines = 1,
                )
            }

            if (!font.valid && font.error.isNotBlank()) {
                Spacer(Modifier.height(9.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(font.error, color = MaterialTheme.colorScheme.error, fontSize = 10.sp)
                }
            }

            Spacer(Modifier.height(11.dp))
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .45f))
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                MiuixLibraryPill(fontCapabilityLabel(font), MaterialTheme.colorScheme.primary)
                Spacer(Modifier.weight(1f))
                if (active) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Rounded.CheckCircle, contentDescription = null, tint = tokens.success, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(5.dp))
                        Text("当前使用", color = tokens.success, fontSize = 12.sp, fontWeight = FontWeight.Black)
                    }
                } else {
                    Surface(
                        modifier = Modifier
                            .clickable(enabled = font.valid && !busy, onClick = onApply),
                        shape = RoundedCornerShape(17.dp),
                        color = if (font.valid && !busy) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 15.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                "应用",
                                color = if (font.valid && !busy) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                                fontWeight = FontWeight.Black,
                                fontSize = 12.sp,
                            )
                            Spacer(Modifier.width(4.dp))
                            Icon(
                                Icons.Rounded.ChevronRight,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp),
                                tint = if (font.valid && !busy) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
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
private fun MiuixLibraryEmpty(query: String) {
    val tokens = LocalMiuixTokens.current
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
                if (query.isBlank()) "还没有导入字体" else "没有匹配的字体",
                color = tokens.textPrimary,
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
            )
            Text(
                if (query.isBlank()) "点击右下角导入按钮添加字体文件" else "清空搜索或尝试其他关键词",
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
        )
    }
}
