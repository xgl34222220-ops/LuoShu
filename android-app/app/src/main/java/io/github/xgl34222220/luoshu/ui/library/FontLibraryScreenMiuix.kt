package io.github.xgl34222220.luoshu.ui.library

import android.view.Gravity
import androidx.compose.foundation.background
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
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Restore
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Sort
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.font.fontCapabilityLabel
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.basic.TextButton
import top.yukonga.miuix.kmp.basic.TextField
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun FontLibraryScreenMiuix(
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    topActions: @Composable () -> Unit = {},
) {
    val colors = MiuixTheme.colorScheme
    var showTools by rememberSaveable { mutableStateOf(false) }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(colors.background),
        contentPadding = PaddingValues(start = 16.dp, top = 18.dp, end = 16.dp, bottom = 112.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(
                modifier = Modifier.padding(horizontal = 4.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "字体库",
                        fontSize = 34.sp,
                        fontWeight = FontWeight.Bold,
                        color = colors.onBackground,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        text = "${state.validCount}/${state.totalCount} 可用 · 当前显示 ${state.visibleCount}",
                        fontSize = 14.sp,
                        color = colors.onSurfaceSecondary,
                    )
                }
                Button(
                    onClick = actions.refresh,
                    enabled = !state.loading,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Refresh,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                    )
                    Text(
                        text = if (state.loading) "读取中" else "刷新",
                        modifier = Modifier.padding(start = 7.dp),
                    )
                }
            }
        }

        item {
            TextField(
                value = state.query,
                onValueChange = actions.setQuery,
                label = "搜索名称、ID 或格式",
                useLabelAsPlaceholder = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = Icons.Rounded.Search,
                    contentDescription = null,
                    tint = colors.primary,
                    modifier = Modifier.size(20.dp),
                )
                FontLibraryFilter.entries.forEach { option ->
                    if (state.filter == option) {
                        Button(onClick = { actions.setFilter(option) }) {
                            Text(option.label)
                        }
                    } else {
                        TextButton(
                            text = option.label,
                            onClick = { actions.setFilter(option) },
                        )
                    }
                }
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "排序方式",
                    summary = state.sort.label,
                    startAction = { MiuixLibraryIcon(Icons.Rounded.Sort) },
                    onClick = {
                        val entries = FontLibrarySort.entries
                        val next = entries[(entries.indexOf(state.sort) + 1) % entries.size]
                        actions.setSort(next)
                    },
                )
                BasicComponent(
                    title = if (showTools) "收起导入与管理" else "导入与管理",
                    summary = "导入字体、整理收藏、标签与归档",
                    startAction = { MiuixLibraryIcon(Icons.Rounded.Tune) },
                    onClick = { showTools = !showTools },
                )
            }
        }

        if (showTools) {
            item { topActions() }
        }

        if (state.error.isNotBlank()) {
            item {
                MiuixLibraryNotice(
                    title = "字体库需要处理",
                    message = state.error,
                    icon = Icons.Rounded.Warning,
                    error = true,
                )
            }
        }
        if (state.operationMessage.isNotBlank()) {
            item {
                MiuixLibraryNotice(
                    title = "字体任务",
                    message = state.operationMessage,
                    icon = Icons.Rounded.CheckCircle,
                    error = false,
                )
            }
        }

        item { MiuixLibrarySectionTitle("系统字体") }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                BasicComponent(
                    title = "系统默认字体",
                    summary = if (state.activeFontId == "default") {
                        "当前正在使用 ROM 原始字体映射"
                    } else {
                        "撤销覆盖并恢复 ROM 原始字体映射"
                    },
                    startAction = { MiuixLibraryIcon(Icons.Rounded.Restore) },
                    enabled = !state.operationBusy,
                    onClick = actions.restoreDefault,
                )
            }
        }

        item { MiuixLibrarySectionTitle("已导入字体") }

        if (!state.loading && state.fonts.isEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    BasicComponent(
                        title = "没有符合条件的字体",
                        summary = "调整搜索或筛选，也可以展开导入与管理工具",
                        startAction = { MiuixLibraryIcon(Icons.Rounded.FontDownload) },
                    )
                }
            }
        }

        items(state.fonts, key = { it.id }) { font ->
            MiuixFontFamilyCard(
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
private fun MiuixFontFamilyCard(
    font: FontItem,
    active: Boolean,
    busy: Boolean,
    onDetails: () -> Unit,
    onApply: () -> Unit,
    onDelete: () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = font.name,
            summary = buildString {
                append(listOf(font.format, font.size, font.date).filter { it.isNotBlank() }.joinToString(" · "))
                val capability = fontCapabilityLabel(font)
                if (capability.isNotBlank()) {
                    if (isNotEmpty()) append("\n")
                    append(capability)
                }
                if (!font.valid && font.error.isNotBlank()) {
                    if (isNotEmpty()) append("\n")
                    append(font.error)
                }
            },
            startAction = { MiuixFontPreviewTile(font) },
            onClick = onDetails,
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 72.dp, end = 16.dp, bottom = 14.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (active) {
                Icon(
                    imageVector = Icons.Rounded.CheckCircle,
                    contentDescription = null,
                    tint = colors.primary,
                    modifier = Modifier.size(20.dp),
                )
                Text(
                    text = "使用中",
                    color = colors.primary,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(start = 6.dp),
                )
            } else {
                TextButton(
                    text = "删除",
                    enabled = !busy,
                    onClick = onDelete,
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = onApply,
                    enabled = font.valid && !busy,
                ) {
                    Text("应用")
                }
            }
        }
    }
}

@Composable
private fun MiuixFontPreviewTile(font: FontItem) {
    val colors = MiuixTheme.colorScheme
    Box(
        modifier = Modifier
            .padding(end = 16.dp)
            .size(50.dp)
            .background(colors.tertiaryContainer, RoundedCornerShape(16.dp)),
        contentAlignment = Alignment.Center,
    ) {
        if (font.valid) {
            NativeFontPreview(
                font = font,
                text = "Aa",
                axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                modifier = Modifier.size(50.dp).padding(5.dp),
                textSizeSp = 18f,
                gravity = Gravity.CENTER,
                maxLines = 1,
            )
        } else {
            Text(
                text = "Aa",
                color = colors.error,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun MiuixLibraryNotice(
    title: String,
    message: String,
    icon: ImageVector,
    error: Boolean,
) {
    val colors = MiuixTheme.colorScheme
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = title,
            summary = message,
            startAction = {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = if (error) colors.error else colors.primary,
                    modifier = Modifier.padding(end = 16.dp).size(24.dp),
                )
            },
        )
    }
}

@Composable
private fun MiuixLibraryIcon(icon: ImageVector) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = MiuixTheme.colorScheme.primary,
        modifier = Modifier.padding(end = 16.dp).size(24.dp),
    )
}

@Composable
private fun MiuixLibrarySectionTitle(title: String) {
    Text(
        text = title,
        color = MiuixTheme.colorScheme.onBackground,
        fontSize = 20.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(start = 4.dp, top = 14.dp, bottom = 2.dp),
    )
}
