package io.github.xgl34222220.luoshu.ui.library

import android.view.Gravity
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
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
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.rememberScrollState
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSmoothShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Delete
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.FontDownload
import androidx.compose.material.icons.rounded.MoreVert
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Sort
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
import androidx.compose.foundation.interaction.MutableInteractionSource
import io.github.xgl34222220.luoshu.ui.theme.luoShuPressScale
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.draw.clip
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalDockContentPadding
import io.github.xgl34222220.luoshu.ui.theme.LocalShowDock
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLayoutTokens
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.luoShuGlassHighlight
import io.github.xgl34222220.luoshu.ui.theme.LuoShuHeaderAction
import io.github.xgl34222220.luoshu.ui.theme.LuoShuLoadingSkeleton
import io.github.xgl34222220.luoshu.ui.theme.LuoShuMotionTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuSectionHeading
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTopBar
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

@Composable
internal fun FontLibraryScreenMiuix(
    style: UiStyle,
    state: FontLibraryUiState,
    actions: FontLibraryActions,
    tools: @Composable () -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val requestShowDock = LocalShowDock.current
    val scheme = MaterialTheme.colorScheme
    val cardColor = tokens.cardBackground
    val elevatedColor = tokens.elevatedCardBackground
    val textPrimary = tokens.textPrimary
    val textSecondary = tokens.textSecondary
    var showTools by rememberSaveable { mutableStateOf(false) }
    var showSort by remember { mutableStateOf(false) }
    val filtered = state.query.isNotBlank() || state.filter != FontLibraryFilter.ALL

    val listState = rememberLazyListState()
    val toolsRevealScope = rememberCoroutineScope()
    var toolsRevealJob by remember { mutableStateOf<Job?>(null) }
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(
            start = LuoShuLayoutTokens.PageHorizontal,
            end = LuoShuLayoutTokens.PageHorizontal,
            bottom = maxOf(LocalDockContentPadding.current, LuoShuLayoutTokens.FloatingDockSafeBottom),
        ),
        verticalArrangement = Arrangement.spacedBy(LuoShuLayoutTokens.ItemGap),
    ) {
        item(key = "header") {
            LuoShuTopBar(title = "字体库") {
                LuoShuHeaderAction(
                    icon = Icons.Rounded.Refresh,
                    contentDescription = "刷新字体库",
                    onClick = actions.refresh,
                    enabled = !state.loading && !state.operationBusy,
                    loading = state.loading,
                    containerColor = elevatedColor,
                )
            }
        }
        item(key = "search") {
            TextField(
                value = state.query,
                onValueChange = actions.setQuery,
                modifier = Modifier.fillMaxWidth().luoShuGlassHighlight(LuoShuSmoothShape(20.dp)),
                textStyle = MaterialTheme.typography.bodyMedium,
                singleLine = true,
                shape = LuoShuSmoothShape(20.dp),
                leadingIcon = { Icon(Icons.Rounded.Search, contentDescription = null) },
                trailingIcon = {
                    if (state.query.isNotEmpty()) {
                        IconButton(onClick = { actions.setQuery("") }) {
                            Icon(Icons.Rounded.Close, contentDescription = "清空搜索")
                        }
                    }
                },
                placeholder = { Text("搜索你的字体") },
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
        item(key = "filters") {
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).selectableGroup(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FontLibraryFilter.entries.forEach { option ->
                    ChoicePill(option.label, state.filter == option) { actions.setFilter(option) }
                }
            }
        }
        item(key = "collection_heading") {
            Column {
                LuoShuSectionHeading(
                    title = if (filtered) "筛选结果" else "本地字体",
                    subtitle = "${state.visibleCount} 款字体 · ${state.validCount} 款可用",
                )
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Box {
                        TextButton(onClick = { showSort = true }) {
                            Icon(Icons.Rounded.Sort, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text(state.sort.label, fontSize = 12.sp)
                            Icon(Icons.Rounded.ExpandMore, contentDescription = null, modifier = Modifier.size(18.dp))
                        }
                        DropdownMenu(expanded = showSort, onDismissRequest = { showSort = false }) {
                            FontLibrarySort.entries.forEach { option ->
                                DropdownMenuItem(
                                    text = { Text(option.label) },
                                    trailingIcon = {
                                        if (state.sort == option) Icon(Icons.Rounded.Check, contentDescription = "已选择")
                                    },
                                    onClick = { actions.setSort(option); showSort = false },
                                )
                            }
                        }
                    }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = {
                        toolsRevealJob?.cancel()
                        showTools = !showTools
                    }) {
                        Text(if (showTools) "收起管理" else "导入与管理", fontSize = 12.sp)
                        Spacer(Modifier.width(4.dp))
                        Icon(
                            if (showTools) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                    }
                }
            }
        }
        item(key = "tools") {
            AnimatedVisibility(
                visible = showTools,
                enter = fadeIn(tween(LuoShuMotionTokens.Fast)) +
                    expandVertically(tween(LuoShuMotionTokens.Normal, easing = FastOutSlowInEasing)) +
                    slideInVertically(tween(LuoShuMotionTokens.Normal, easing = FastOutSlowInEasing)) { it / 6 },
                exit = fadeOut(tween(140)) +
                    shrinkVertically(tween(170, easing = FastOutSlowInEasing)),
            ) {
                tools()
            }
        }
        if (state.loading) {
            item(key = "loading") {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    LuoShuLoadingSkeleton(
                        modifier = Modifier.fillMaxWidth(.42f).height(14.dp),
                    )
                    LuoShuLoadingSkeleton(
                        modifier = Modifier.fillMaxWidth().height(5.dp),
                        shape = LuoShuSmoothShape(999.dp),
                    )
                }
            }
        } else if (state.operationRunning) {
            item(key = "loading") {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("正在处理字体，请稍候…", color = textSecondary, fontSize = 13.sp)
                    LinearProgressIndicator(Modifier.fillMaxWidth().height(4.dp))
                }
            }
        }
        if (state.error.isNotBlank()) item(key = "error") { NoticeCard(state.error, error = true) }
        if (state.operationMessage.isNotBlank()) {
            item(key = "operation") { NoticeCard(state.operationMessage, error = false) }
        }
        item(key = "system_font") {
            MiuixSystemFontRow(
                active = state.activeFontId == "default", busy = state.operationBusy,
                cardColor = cardColor, textPrimary = textPrimary, textSecondary = textSecondary,
                onRestore = actions.restoreDefault,
            )
        }
        if (!state.loading && state.fonts.isEmpty()) {
            item(key = "empty") {
                Card(
                    modifier = Modifier.fillMaxWidth().luoShuGlassHighlight(LuoShuSmoothShape(24.dp)),
                    shape = LuoShuSmoothShape(24.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = tokens.cardShadowElevation),
                    colors = CardDefaults.cardColors(containerColor = cardColor),
                    border = BorderStroke(1.dp, tokens.glassOutlineBrush),
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Surface(shape = LuoShuSmoothShape(22.dp), color = scheme.primary.copy(alpha = .08f)) {
                            Icon(
                                if (filtered) Icons.Rounded.Search else Icons.Rounded.FontDownload,
                                contentDescription = null, tint = scheme.primary,
                                modifier = Modifier.padding(18.dp).size(30.dp),
                            )
                        }
                        Text(
                            if (filtered) "没有找到匹配的字体" else "从第一款字体开始",
                            color = textPrimary, fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
                            textAlign = TextAlign.Center,
                        )
                        Text(
                            if (filtered) "试试其他关键词，或清除筛选条件。" else "导入喜欢的字体，在这里预览、整理和应用。",
                            color = textSecondary, fontSize = 13.sp, lineHeight = 20.sp,
                            textAlign = TextAlign.Center,
                        )
                        FilledTonalButton(onClick = {
                            if (filtered) { actions.setQuery(""); actions.setFilter(FontLibraryFilter.ALL) }
                            else {
                                toolsRevealJob?.cancel()
                                // Restore navigation in this tap, never in a delayed scroll completion.
                                requestShowDock()
                                showTools = true
                                toolsRevealJob = toolsRevealScope.launch {
                                    // collection_heading is the fourth fixed item, before any status rows.
                                    // Reveal it and the tools below in the next frame; newer taps, user
                                    // scrolls and page disposal can cancel this one navigation request.
                                    withFrameNanos { }
                                    listState.animateScrollToItem(index = 3)
                                }
                            }
                        }) { Text(if (filtered) "清除筛选" else "打开导入与管理") }
                    }
                }
            }
        }
        items(state.fonts, key = { "font:${it.id}" }, contentType = { "font" }) { font ->
            MiuixFontRow(
                font = font, active = state.activeFontId == font.id, busy = state.operationBusy,
                cardColor = cardColor, textPrimary = textPrimary, textSecondary = textSecondary,
                onDetails = { actions.details(font) }, onApply = { actions.apply(font) },
                onDelete = { actions.delete(font) },
            )
        }
    }
}

@Composable
private fun MiuixSystemFontRow(
    active: Boolean, busy: Boolean, cardColor: Color,
    textPrimary: Color, textSecondary: Color, onRestore: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth().luoShuGlassHighlight(LuoShuSmoothShape(24.dp)),
        shape = LuoShuSmoothShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = cardColor),
        border = BorderStroke(
            1.dp,
            LocalMiuixTokens.current.glassOutlineBrush,
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = LocalMiuixTokens.current.cardShadowElevation),
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = LuoShuSmoothShape(16.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = .08f)) {
                Box(Modifier.size(48.dp), contentAlignment = Alignment.Center) {
                    Text("Aa", color = MaterialTheme.colorScheme.primary, fontSize = 21.sp, fontWeight = FontWeight.Medium)
                }
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("系统默认", color = textPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Text("恢复手机原有字体", color = textSecondary, fontSize = 12.sp, lineHeight = 18.sp)
            }
            Spacer(Modifier.width(8.dp))
            if (active) StatusPill("使用中")
            else FilledTonalButton(
                onClick = onRestore, enabled = !busy,
                modifier = Modifier.heightIn(min = 44.dp), shape = LuoShuSmoothShape(16.dp),
                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 8.dp),
            ) { Text("恢复", fontSize = 13.sp) }
        }
    }
}

@Composable
private fun MiuixFontRow(
    font: FontItem, active: Boolean, busy: Boolean, cardColor: Color,
    textPrimary: Color, textSecondary: Color,
    onDetails: () -> Unit, onApply: () -> Unit, onDelete: () -> Unit,
) {
    var menuExpanded by remember(font.id) { mutableStateOf(false) }
    val interactionSource = remember(font.id) { MutableInteractionSource() }
    val scheme = MaterialTheme.colorScheme
    Card(
        onClick = onDetails,
        interactionSource = interactionSource,
        modifier = Modifier.fillMaxWidth().luoShuPressScale(interactionSource, pressedScale = .985f)
            .luoShuGlassHighlight(LuoShuSmoothShape(24.dp)),
        shape = LuoShuSmoothShape(24.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (font.valid) cardColor else scheme.errorContainer.copy(alpha = .34f),
        ),
        border = if (!font.valid) BorderStroke(1.dp, scheme.error.copy(alpha = .16f))
            else BorderStroke(1.dp, LocalMiuixTokens.current.glassOutlineBrush),
        elevation = CardDefaults.cardElevation(defaultElevation = LocalMiuixTokens.current.cardShadowElevation),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(
                        font.name, color = textPrimary, fontSize = 16.sp, lineHeight = 22.sp,
                        fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        fontMetadataSummary(font),
                        color = textSecondary,
                        fontSize = 12.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                if (active) StatusPill("使用中")
                Box {
                    IconButton(onClick = { menuExpanded = true }, modifier = Modifier.size(48.dp)) {
                        Icon(Icons.Rounded.MoreVert, contentDescription = "${font.name}的更多操作", tint = textSecondary)
                    }
                    DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                        DropdownMenuItem(text = { Text("字体详情") }, onClick = { menuExpanded = false; onDetails() })
                        DropdownMenuItem(
                            text = { Text("删除字体") },
                            leadingIcon = { Icon(Icons.Rounded.Delete, contentDescription = null) },
                            enabled = !busy && !active,
                            onClick = { menuExpanded = false; onDelete() },
                        )
                    }
                }
            }
            if (font.valid) {
                Surface(
                    shape = LuoShuSmoothShape(18.dp),
                    color = LocalMiuixTokens.current.insetBackground,
                    border = BorderStroke(1.dp, if (active) scheme.primary.copy(alpha = .20f)
                        else LocalMiuixTokens.current.insetOutline),
                ) {
                    NativeFontPreview(
                        font = font,
                        text = if (font.supportsCjk) "山海有相逢 Aa 0123" else "Hello, LuoShu 0123",
                        axes = if (font.variable) mapOf("wght" to 400f) else emptyMap(),
                        modifier = Modifier.fillMaxWidth().height(70.dp).padding(horizontal = 14.dp),
                        textSizeSp = 22f, gravity = Gravity.CENTER_VERTICAL, maxLines = 1,
                    )
                }
            } else if (font.error.isNotBlank()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Rounded.Warning, contentDescription = null, tint = scheme.error, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(font.error, color = scheme.error, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "轻触卡片查看详情",
                    modifier = Modifier.weight(1f),
                    color = textSecondary,
                    fontSize = 11.sp,
                )
                Spacer(Modifier.width(12.dp))
                if (active) {
                    FilledTonalButton(onClick = onDetails, modifier = Modifier.heightIn(min = 44.dp), shape = LuoShuSmoothShape(16.dp)) {
                        Text("查看详情", fontSize = 13.sp)
                    }
                } else {
                    Button(
                        onClick = onApply, enabled = font.valid && !busy,
                        modifier = Modifier.heightIn(min = 44.dp), shape = LuoShuSmoothShape(16.dp),
                        contentPadding = PaddingValues(horizontal = 22.dp, vertical = 8.dp),
                    ) { Text("应用字体", fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }
                }
            }
        }
    }
}

private fun fontMetadataSummary(font: FontItem): String {
    val weight = when {
        font.variable -> "可变字重"
        font.weights.size > 1 -> "${font.weights.size} 档字重"
        else -> "单字重"
    }
    return listOf(
        font.format,
        font.size,
        weight,
        if (font.supportsCjk) "中文 / 拉丁" else "拉丁",
    ).filter { it.isNotBlank() }.joinToString(" · ")
}

@Composable
private fun ChoicePill(label: String, active: Boolean, onClick: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val containerColor by animateColorAsState(
        targetValue = if (active) scheme.primary else LocalMiuixTokens.current.elevatedCardBackground,
        animationSpec = tween(LuoShuMotionTokens.Fast),
        label = "fontFilterColor",
    )
    // A compact visible pill keeps the full 48 dp selectable touch region.
    Box(
        modifier = Modifier.defaultMinSize(minHeight = 48.dp).clip(LuoShuSmoothShape(16.dp))
            .selectable(selected = active, role = Role.Tab, onClick = onClick)
            .padding(vertical = 4.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            shape = LuoShuSmoothShape(14.dp),
            color = containerColor,
            border = BorderStroke(1.dp, if (active) scheme.primary.copy(alpha = .28f)
                else LocalMiuixTokens.current.insetOutline),
        ) {
            Row(
                Modifier.heightIn(min = 40.dp).padding(horizontal = 14.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(5.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (active) Icon(Icons.Rounded.Check, null, tint = scheme.onPrimary, modifier = Modifier.size(14.dp))
                Text(label, color = if (active) scheme.onPrimary else LocalMiuixTokens.current.textPrimary,
                    style = MaterialTheme.typography.labelLarge, fontWeight = if (active) FontWeight.SemiBold else FontWeight.Medium)
            }
        }
    }
}

@Composable
private fun NoticeCard(message: String, error: Boolean) {
    val scheme = MaterialTheme.colorScheme
    Surface(
        shape = LuoShuSmoothShape(20.dp),
        color = if (error) scheme.errorContainer else scheme.primaryContainer,
    ) {
        Text(
            message, modifier = Modifier.fillMaxWidth().padding(16.dp),
            color = if (error) scheme.onErrorContainer else scheme.onPrimaryContainer,
            fontSize = 13.sp, lineHeight = 20.sp,
        )
    }
}

@Composable
private fun StatusPill(text: String) {
    val scheme = MaterialTheme.colorScheme
    Surface(shape = LuoShuSmoothShape(12.dp), color = scheme.primary.copy(alpha = .10f)) {
        Row(Modifier.padding(horizontal = 9.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.Check, contentDescription = null, tint = scheme.primary, modifier = Modifier.size(13.dp))
            Spacer(Modifier.width(3.dp))
            Text(text, color = scheme.primary, fontSize = 11.sp, fontWeight = FontWeight.Medium)
        }
    }
}
