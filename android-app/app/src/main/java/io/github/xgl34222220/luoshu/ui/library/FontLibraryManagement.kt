package io.github.xgl34222220.luoshu.ui.library

import android.content.Context
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
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Label
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material.icons.rounded.Star
import androidx.compose.material.icons.rounded.StarBorder
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import org.json.JSONArray
import org.json.JSONObject

internal val fontLibraryTagOptions = listOf("正文", "标题", "英文", "数字", "候选", "待整理")

@Immutable
internal data class FontLibraryCollections(
    val favoriteIds: Set<String> = emptySet(),
    val tags: Map<String, Set<String>> = emptyMap(),
) {
    fun clean(validIds: Set<String>): FontLibraryCollections = copy(
        favoriteIds = favoriteIds.intersect(validIds),
        tags = tags.mapNotNull { (fontId, values) ->
            if (fontId !in validIds) null else fontId to values.intersect(fontLibraryTagOptions.toSet())
        }.filterValues { it.isNotEmpty() }.toMap(),
    )
}

internal class FontLibraryCollectionStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences(
        "font-library-collections-v1",
        Context.MODE_PRIVATE,
    )

    fun load(): FontLibraryCollections = runCatching {
        val root = JSONObject(preferences.getString("collections", "{}") ?: "{}")
        val favoritesArray = root.optJSONArray("favorites") ?: JSONArray()
        val favorites = buildSet {
            for (index in 0 until favoritesArray.length()) {
                favoritesArray.optString(index).trim().takeIf { it.isNotBlank() }?.let(::add)
            }
        }
        val tagsObject = root.optJSONObject("tags") ?: JSONObject()
        val tags = buildMap {
            val keys = tagsObject.keys()
            while (keys.hasNext()) {
                val fontId = keys.next()
                val valuesArray = tagsObject.optJSONArray(fontId) ?: continue
                val values = buildSet {
                    for (index in 0 until valuesArray.length()) {
                        valuesArray.optString(index).trim().takeIf { it in fontLibraryTagOptions }?.let(::add)
                    }
                }
                if (values.isNotEmpty()) put(fontId, values)
            }
        }
        FontLibraryCollections(favorites, tags)
    }.getOrDefault(FontLibraryCollections())

    fun save(collections: FontLibraryCollections) {
        val root = JSONObject()
            .put("favorites", JSONArray(collections.favoriteIds.sorted()))
            .put(
                "tags",
                JSONObject().apply {
                    collections.tags.toSortedMap().forEach { (fontId, values) ->
                        put(fontId, JSONArray(values.sorted()))
                    }
                },
            )
        preferences.edit().putString("collections", root.toString()).apply()
    }
}

internal enum class FontFamilyBucket(val label: String, val description: String) {
    VARIABLE("可变字体家族", "一个字体文件覆盖连续字重或更多设计轴"),
    STATIC("静态字体家族", "同一 Family 下包含多个独立字重文件"),
    SINGLE("单字体", "当前 Family 只有一个可用字重"),
    INVALID("需要检查", "格式、完整性或字体门禁未通过"),
}

@Immutable
internal data class FontFamilySection(
    val bucket: FontFamilyBucket,
    val fonts: List<FontItem>,
)

@Immutable
internal data class FontLibraryConflictReport(
    val duplicateIds: Set<String> = emptySet(),
    val nameConflictIds: Set<String> = emptySet(),
    val messages: Map<String, String> = emptyMap(),
) {
    val issueIds: Set<String> get() = duplicateIds + nameConflictIds
}

internal fun groupFontFamilies(fonts: List<FontItem>): List<FontFamilySection> {
    val buckets = fonts.groupBy { font ->
        when {
            !font.valid -> FontFamilyBucket.INVALID
            font.variable -> FontFamilyBucket.VARIABLE
            font.weights.size >= 2 -> FontFamilyBucket.STATIC
            else -> FontFamilyBucket.SINGLE
        }
    }
    return FontFamilyBucket.entries.mapNotNull { bucket ->
        buckets[bucket]
            ?.sortedWith(compareBy<FontItem> { it.name.lowercase() }.thenBy { it.id })
            ?.takeIf { it.isNotEmpty() }
            ?.let { FontFamilySection(bucket, it) }
    }
}

internal fun analyzeFontLibraryConflicts(fonts: List<FontItem>): FontLibraryConflictReport {
    val duplicateIds = linkedSetOf<String>()
    val nameConflictIds = linkedSetOf<String>()
    val messages = linkedMapOf<String, String>()

    fonts.groupBy(::canonicalFamilyKey).values.filter { it.size >= 2 }.forEach { group ->
        val signatures = group.map(::fontResourceSignature).toSet()
        val ids = group.map { it.id }.toSet()
        if (signatures.size == 1 && signatures.none { it.contains("|unknown|") }) {
            duplicateIds += ids
            group.forEach { messages[it.id] = "Family 名称和资源特征高度一致，疑似重复导入" }
        } else {
            nameConflictIds += ids
            group.forEach { messages[it.id] = "Family 名称接近，但格式、大小或字重结构不同" }
        }
    }

    return FontLibraryConflictReport(
        duplicateIds = duplicateIds,
        nameConflictIds = nameConflictIds,
        messages = messages,
    )
}

internal fun toggleFontFavorite(
    collections: FontLibraryCollections,
    fontIds: Set<String>,
): FontLibraryCollections {
    if (fontIds.isEmpty()) return collections
    val remove = fontIds.all { it in collections.favoriteIds }
    return collections.copy(
        favoriteIds = if (remove) collections.favoriteIds - fontIds else collections.favoriteIds + fontIds,
    )
}

internal fun toggleFontTag(
    collections: FontLibraryCollections,
    fontIds: Set<String>,
    tag: String,
): FontLibraryCollections {
    if (fontIds.isEmpty() || tag !in fontLibraryTagOptions) return collections
    val remove = fontIds.all { tag in collections.tags[it].orEmpty() }
    val updated = collections.tags.toMutableMap()
    fontIds.forEach { fontId ->
        val values = updated[fontId].orEmpty().toMutableSet()
        if (remove) values.remove(tag) else values.add(tag)
        if (values.isEmpty()) updated.remove(fontId) else updated[fontId] = values
    }
    return collections.copy(tags = updated.toMap())
}

private fun canonicalFamilyKey(font: FontItem): String {
    val source = font.name.ifBlank { font.id }.lowercase()
        .replace(Regex("(?:\\s|[-_])*(?:copy|副本|拷贝)(?:\\s*\\d+)?$"), "")
        .replace(Regex("(?:\\s|[-_])*\\(\\d+\\)$"), "")
        .replace(Regex("(?:\\s|[-_])+\\d+$"), "")
    return source.replace(Regex("[^a-z0-9\\u4e00-\\u9fff]+"), "")
        .ifBlank { font.id.lowercase() }
}

private fun fontResourceSignature(font: FontItem): String = buildString {
    append(font.format.lowercase().ifBlank { "unknown" })
    append('|').append(font.size.lowercase().ifBlank { "unknown" })
    append('|').append(if (font.variable) "variable" else "static")
    append('|').append(font.weights.sorted().joinToString(",").ifBlank { "regular" })
    append('|').append(font.supportsCjk)
}

@Composable
internal fun FontLibraryManagementButton(
    style: UiStyle,
    favoriteCount: Int,
    issueCount: Int,
    loading: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        onClick = onClick,
        enabled = !loading,
        modifier = modifier,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 19.dp),
        color = MaterialTheme.colorScheme.primary,
        contentColor = MaterialTheme.colorScheme.onPrimary,
        shadowElevation = 9.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 15.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (loading) {
                CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
            } else {
                Icon(Icons.Rounded.ListAlt, contentDescription = null, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(8.dp))
            Column {
                Text("管理字体库", fontSize = 11.sp, fontWeight = FontWeight.Black)
                Text("收藏 $favoriteCount · 提示 $issueCount", fontSize = 9.sp, color = MaterialTheme.colorScheme.onPrimary.copy(alpha = .75f))
            }
        }
    }
}

@Composable
internal fun FontLibraryManagementDialog(
    style: UiStyle,
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

    fun updateCollections(next: FontLibraryCollections) {
        onCollectionsChange(next.clean(allIds))
    }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 760.dp),
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            color = MaterialTheme.colorScheme.surfaceContainerHigh,
            shadowElevation = 12.dp,
        ) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 15.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(
                        modifier = Modifier.size(46.dp),
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.primaryContainer,
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(Icons.Rounded.ListAlt, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Family 与收藏管理", fontSize = 19.sp, fontWeight = FontWeight.Black)
                        Text(
                            "${fonts.size} 个 Family · ${collections.favoriteIds.size} 个收藏 · ${conflicts.issueIds.size} 个提示",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                        )
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Rounded.Close, contentDescription = "关闭")
                    }
                }

                Spacer(Modifier.size(12.dp))
                ManagementBatchPanel(
                    selectedIds = selectedIds,
                    allIds = allIds,
                    collections = collections,
                    onSelectAll = { selectedIds = if (selectedIds.size == allIds.size) emptySet() else allIds },
                    onClear = { selectedIds = emptySet() },
                    onToggleFavorite = { updateCollections(toggleFontFavorite(collections, selectedIds)) },
                    onToggleTag = { tag -> updateCollections(toggleFontTag(collections, selectedIds, tag)) },
                )
                Spacer(Modifier.size(10.dp))

                LazyColumn(
                    modifier = Modifier.weight(1f, fill = false),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    sections.forEach { section ->
                        item(key = "header-${section.bucket.name}") {
                            Column(Modifier.padding(top = 5.dp, bottom = 2.dp)) {
                                Text(section.bucket.label, fontSize = 15.sp, fontWeight = FontWeight.Black)
                                Text(section.bucket.description, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
                            }
                        }
                        items(section.fonts, key = { it.id }) { font ->
                            ManagementFamilyRow(
                                font = font,
                                active = font.id == activeFontId,
                                selected = font.id in selectedIds,
                                favorite = font.id in collections.favoriteIds,
                                tags = collections.tags[font.id].orEmpty(),
                                conflictMessage = conflicts.messages[font.id].orEmpty(),
                                duplicate = font.id in conflicts.duplicateIds,
                                onSelect = {
                                    selectedIds = if (font.id in selectedIds) selectedIds - font.id else selectedIds + font.id
                                },
                                onFavorite = {
                                    updateCollections(toggleFontFavorite(collections, setOf(font.id)))
                                },
                                onDetails = { onOpenDetails(font) },
                            )
                        }
                    }
                }

                Spacer(Modifier.size(10.dp))
                TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) {
                    Text("完成", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun ManagementBatchPanel(
    selectedIds: Set<String>,
    allIds: Set<String>,
    collections: FontLibraryCollections,
    onSelectAll: () -> Unit,
    onClear: () -> Unit,
    onToggleFavorite: () -> Unit,
    onToggleTag: (String) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("批量整理", fontSize = 13.sp, fontWeight = FontWeight.Black)
                    Text(
                        if (selectedIds.isEmpty()) "选择 Family 后可批量收藏或添加标签" else "已选择 ${selectedIds.size} 个 Family",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 9.sp,
                    )
                }
                TextButton(onClick = onSelectAll, enabled = allIds.isNotEmpty()) {
                    Text(if (selectedIds.size == allIds.size && allIds.isNotEmpty()) "取消全选" else "全选")
                }
                if (selectedIds.isNotEmpty()) {
                    TextButton(onClick = onClear) { Text("清空") }
                }
            }
            if (selectedIds.isNotEmpty()) {
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    val allFavorite = selectedIds.all { it in collections.favoriteIds }
                    ManagementActionPill(
                        label = if (allFavorite) "取消收藏" else "加入收藏",
                        active = allFavorite,
                        icon = if (allFavorite) Icons.Rounded.Star else Icons.Rounded.StarBorder,
                        onClick = onToggleFavorite,
                    )
                    fontLibraryTagOptions.forEach { tag ->
                        val active = selectedIds.all { tag in collections.tags[it].orEmpty() }
                        ManagementActionPill(
                            label = tag,
                            active = active,
                            icon = Icons.Rounded.Label,
                            onClick = { onToggleTag(tag) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ManagementActionPill(
    label: String,
    active: Boolean,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(999.dp),
        color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceContainerHigh,
        contentColor = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(15.dp))
            Spacer(Modifier.width(5.dp))
            Text(label, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun ManagementFamilyRow(
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
    val warning = conflictMessage.isNotBlank()
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = when {
            !font.valid -> MaterialTheme.colorScheme.errorContainer.copy(alpha = .52f)
            selected -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = .62f)
            else -> MaterialTheme.colorScheme.surfaceContainerLow
        },
        shadowElevation = if (selected) 3.dp else 0.dp,
    ) {
        Column(Modifier.padding(11.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = selected, onCheckedChange = { onSelect() })
                Surface(
                    modifier = Modifier.size(42.dp).clickable(onClick = onDetails),
                    shape = RoundedCornerShape(14.dp),
                    color = MaterialTheme.colorScheme.primaryContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Aa", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                    }
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f).clickable(onClick = onDetails)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            font.name,
                            modifier = Modifier.weight(1f),
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Black,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (active) ManagementStatusPill("使用中", MaterialTheme.colorScheme.primary)
                    }
                    Text(
                        familyStructureLabel(font),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 9.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                IconButton(onClick = onFavorite, modifier = Modifier.size(40.dp)) {
                    Icon(
                        if (favorite) Icons.Rounded.Star else Icons.Rounded.StarBorder,
                        contentDescription = if (favorite) "取消收藏" else "收藏字体",
                        tint = if (favorite) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            if (tags.isNotEmpty() || warning || !font.valid) {
                Spacer(Modifier.size(7.dp))
                Row(
                    modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    tags.sorted().forEach { tag -> ManagementStatusPill(tag, MaterialTheme.colorScheme.secondary) }
                    if (warning) {
                        ManagementStatusPill(
                            if (duplicate) "疑似重复" else "命名冲突",
                            MaterialTheme.colorScheme.error,
                            warning = true,
                        )
                    }
                    if (!font.valid) ManagementStatusPill("需检查", MaterialTheme.colorScheme.error, warning = true)
                }
                if (warning) {
                    Spacer(Modifier.size(5.dp))
                    Text(
                        conflictMessage,
                        color = MaterialTheme.colorScheme.error,
                        fontSize = 9.sp,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

private fun familyStructureLabel(font: FontItem): String = when {
    !font.valid -> font.error.ifBlank { "字体检查未通过" }
    font.variable -> "可变 Family · 连续设计轴 · ${font.format}"
    font.weights.size >= 2 -> "静态 Family · ${font.weights.size} 个字重 · ${font.format}"
    else -> "单字体 · ${font.weightLabel} · ${font.format}"
}

@Composable
private fun ManagementStatusPill(
    text: String,
    color: Color,
    warning: Boolean = false,
) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = .12f), contentColor = color) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (warning) {
                Icon(Icons.Rounded.Warning, contentDescription = null, modifier = Modifier.size(13.dp))
                Spacer(Modifier.width(4.dp))
            } else if (text == "使用中") {
                Icon(Icons.Rounded.CheckCircle, contentDescription = null, modifier = Modifier.size(13.dp))
                Spacer(Modifier.width(4.dp))
            }
            Text(text, fontSize = 9.sp, fontWeight = FontWeight.Black, maxLines = 1)
        }
    }
}
