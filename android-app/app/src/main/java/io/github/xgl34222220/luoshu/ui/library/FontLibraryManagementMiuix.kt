package io.github.xgl34222220.luoshu.ui.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Label
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarBorder
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.state.ToggleableState
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.FontItem
import top.yukonga.miuix.kmp.basic.BasicComponent
import top.yukonga.miuix.kmp.basic.Button
import top.yukonga.miuix.kmp.basic.Card
import top.yukonga.miuix.kmp.basic.Checkbox
import top.yukonga.miuix.kmp.basic.CircularProgressIndicator
import top.yukonga.miuix.kmp.basic.Icon
import top.yukonga.miuix.kmp.basic.Text
import top.yukonga.miuix.kmp.basic.TextButton
import top.yukonga.miuix.kmp.overlay.OverlayDialog
import top.yukonga.miuix.kmp.theme.MiuixTheme

@Composable
internal fun FontLibraryManagementButtonMiuix(
    favoriteCount: Int,
    issueCount: Int,
    loading: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Button(
        onClick = onClick,
        enabled = !loading,
        modifier = modifier,
    ) {
        if (loading) {
            CircularProgressIndicator(
                progress = null,
                modifier = Modifier.size(20.dp),
            )
        } else {
            Icon(
                imageVector = Icons.Rounded.ListAlt,
                contentDescription = null,
                modifier = Modifier.size(21.dp),
            )
        }
        Column(modifier = Modifier.padding(start = 10.dp)) {
            Text("管理字体库", fontWeight = FontWeight.Bold)
            Text(
                text = "收藏 $favoriteCount · 提示 $issueCount",
                fontSize = 11.sp,
                color = MiuixTheme.colorScheme.onPrimary.copy(alpha = .74f),
            )
        }
    }
}

@Composable
internal fun FontLibraryManagementDialogMiuix(
    fonts: List<FontItem>,
    activeFontId: String,
    collections: FontLibraryCollections,
    conflicts: FontLibraryConflictReport,
    onCollectionsChange: (FontLibraryCollections) -> Unit,
    onOpenDetails: (FontItem) -> Unit,
    onDismiss: () -> Unit,
) {
    var selectedIds by remember(fonts) { mutableStateOf(emptySet<String>()) }
    val sections = remember(fonts) { groupFontFamilies(fonts) }
    val allIds = remember(fonts) { fonts.map { it.id }.toSet() }

    OverlayDialog(
        title = "Family 与收藏管理",
        summary = "${fonts.size} 个 Family · ${collections.favoriteIds.size} 个收藏 · ${conflicts.issueIds.size} 个提示",
        show = true,
        onDismissRequest = onDismiss,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            MiuixManagementBatchPanel(
                selectedIds = selectedIds,
                allIds = allIds,
                collections = collections,
                onSelectAll = {
                    selectedIds = if (selectedIds.size == allIds.size) emptySet() else allIds
                },
                onClear = { selectedIds = emptySet() },
                onToggleFavorite = {
                    onCollectionsChange(toggleFontFavorite(collections, selectedIds))
                },
                onToggleTag = { tag ->
                    onCollectionsChange(toggleFontTag(collections, selectedIds, tag))
                },
            )

            LazyColumn(
                modifier = Modifier.fillMaxWidth().heightIn(max = 520.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                sections.forEach { section ->
                    item(key = "miuix-header-${section.bucket.name}") {
                        Column(Modifier.padding(start = 4.dp, top = 7.dp, bottom = 2.dp)) {
                            Text(
                                text = section.bucket.label,
                                fontSize = 17.sp,
                                fontWeight = FontWeight.Bold,
                                color = MiuixTheme.colorScheme.onBackground,
                            )
                            Text(
                                text = section.bucket.description,
                                fontSize = 11.sp,
                                color = MiuixTheme.colorScheme.onSurfaceSecondary,
                            )
                        }
                    }
                    items(section.fonts, key = { it.id }) { font ->
                        MiuixManagementFamilyRow(
                            font = font,
                            active = font.id == activeFontId,
                            selected = font.id in selectedIds,
                            favorite = font.id in collections.favoriteIds,
                            tags = collections.tags[font.id].orEmpty(),
                            conflictMessage = conflicts.messages[font.id].orEmpty(),
                            duplicate = font.id in conflicts.duplicateIds,
                            onSelect = {
                                selectedIds = if (font.id in selectedIds) {
                                    selectedIds - font.id
                                } else {
                                    selectedIds + font.id
                                }
                            },
                            onFavorite = {
                                onCollectionsChange(toggleFontFavorite(collections, setOf(font.id)))
                            },
                            onDetails = { onOpenDetails(font) },
                        )
                    }
                }
            }

            Button(
                onClick = onDismiss,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("完成", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun MiuixManagementBatchPanel(
    selectedIds: Set<String>,
    allIds: Set<String>,
    collections: FontLibraryCollections,
    onSelectAll: () -> Unit,
    onClear: () -> Unit,
    onToggleFavorite: () -> Unit,
    onToggleTag: (String) -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        BasicComponent(
            title = "批量整理",
            summary = if (selectedIds.isEmpty()) {
                "选择 Family 后可批量收藏或添加标签"
            } else {
                "已选择 ${selectedIds.size} 个 Family"
            },
            startAction = {
                MiuixManagementIcon(Icons.Rounded.Label)
            },
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(
                text = if (selectedIds.size == allIds.size && allIds.isNotEmpty()) "取消全选" else "全选",
                enabled = allIds.isNotEmpty(),
                onClick = onSelectAll,
            )
            if (selectedIds.isNotEmpty()) {
                Spacer(Modifier.width(8.dp))
                TextButton(text = "清空", onClick = onClear)
            }
        }
        if (selectedIds.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                val allFavorite = selectedIds.all { it in collections.favoriteIds }
                MiuixManagementAction(
                    label = if (allFavorite) "取消收藏" else "加入收藏",
                    active = allFavorite,
                    icon = if (allFavorite) Icons.Rounded.Star else Icons.Rounded.StarBorder,
                    onClick = onToggleFavorite,
                )
                fontLibraryTagOptions.forEach { tag ->
                    MiuixManagementAction(
                        label = tag,
                        active = selectedIds.all { tag in collections.tags[it].orEmpty() },
                        icon = Icons.Rounded.Label,
                        onClick = { onToggleTag(tag) },
                    )
                }
            }
        }
    }
}

@Composable
private fun MiuixManagementAction(
    label: String,
    active: Boolean,
    icon: ImageVector,
    onClick: () -> Unit,
) {
    if (active) {
        Button(onClick = onClick) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(17.dp))
            Text(label, modifier = Modifier.padding(start = 6.dp))
        }
    } else {
        TextButton(text = label, onClick = onClick)
    }
}

@Composable
private fun MiuixManagementFamilyRow(
    font: FontItem,
    active: Boolean,
    selected: Boolean,
    favorite: Boolean,
    tags: Set<String>,
    conflictMessage: String,
    duplicate: Boolean,
    onSelect: () -> Unit,
    onFavorite: () -> Unit,
    onDetails: () -> Unit,
) {
    val colors = MiuixTheme.colorScheme
    val warning = conflictMessage.isNotBlank()
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    color = when {
                        !font.valid -> colors.errorContainer.copy(alpha = .52f)
                        selected -> colors.primaryContainer.copy(alpha = .62f)
                        else -> Color.Transparent
                    },
                    shape = RoundedCornerShape(24.dp),
                )
                .padding(horizontal = 14.dp, vertical = 13.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Checkbox(
                state = if (selected) ToggleableState.On else ToggleableState.Off,
                onClick = onSelect,
            )
            Spacer(Modifier.width(11.dp))
            Box(
                modifier = Modifier
                    .size(46.dp)
                    .background(colors.tertiaryContainer, RoundedCornerShape(16.dp))
                    .clickable(onClick = onDetails),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = "Aa",
                    color = colors.primary,
                    fontWeight = FontWeight.Bold,
                )
            }
            Spacer(Modifier.width(11.dp))
            Column(
                modifier = Modifier
                    .weight(1f)
                    .clickable(onClick = onDetails),
            ) {
                Text(
                    text = font.name,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    color = colors.onBackground,
                )
                Text(
                    text = miuixFamilyStructureLabel(font),
                    fontSize = 10.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    color = colors.onSurfaceSecondary,
                )
                if (active || tags.isNotEmpty() || warning || !font.valid) {
                    Spacer(Modifier.size(6.dp))
                    Row(
                        modifier = Modifier.horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        if (active) {
                            MiuixManagementTag("使用中", colors.primary, Icons.Rounded.CheckCircle)
                        }
                        tags.sorted().forEach { tag ->
                            MiuixManagementTag(tag, colors.secondary, Icons.Rounded.Label)
                        }
                        if (warning) {
                            MiuixManagementTag(
                                if (duplicate) "疑似重复" else "命名冲突",
                                colors.error,
                                Icons.Rounded.Warning,
                            )
                        }
                        if (!font.valid) {
                            MiuixManagementTag("需检查", colors.error, Icons.Rounded.Warning)
                        }
                    }
                }
                if (warning) {
                    Spacer(Modifier.size(5.dp))
                    Text(
                        text = conflictMessage,
                        fontSize = 10.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        color = colors.error,
                    )
                }
            }
            Spacer(Modifier.width(8.dp))
            TextButton(
                text = if (favorite) "已收藏" else "收藏",
                onClick = onFavorite,
            )
        }
    }
}

@Composable
private fun MiuixManagementTag(
    text: String,
    color: Color,
    icon: ImageVector,
) {
    Row(
        modifier = Modifier
            .background(color.copy(alpha = .12f), RoundedCornerShape(999.dp))
            .padding(horizontal = 8.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = color,
            modifier = Modifier.size(13.dp),
        )
        Spacer(Modifier.width(4.dp))
        Text(
            text = text,
            color = color,
            fontSize = 9.sp,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
    }
}

@Composable
private fun MiuixManagementIcon(icon: ImageVector) {
    Icon(
        imageVector = icon,
        contentDescription = null,
        tint = MiuixTheme.colorScheme.primary,
        modifier = Modifier.padding(end = 16.dp).size(24.dp),
    )
}

private fun miuixFamilyStructureLabel(font: FontItem): String = when {
    !font.valid -> font.error.ifBlank { "字体检查未通过" }
    font.variable -> "可变 Family · 连续设计轴 · ${font.format}"
    font.weights.size >= 2 -> "静态 Family · ${font.weights.size} 个字重 · ${font.format}"
    else -> "单字体 · ${font.weightLabel} · ${font.format}"
}
