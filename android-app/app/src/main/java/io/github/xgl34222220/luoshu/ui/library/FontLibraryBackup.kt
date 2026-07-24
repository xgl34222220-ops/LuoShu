package io.github.xgl34222220.luoshu.ui.library

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material.icons.rounded.FileUpload
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.BuildConfig
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.studio.FontStudioActions
import io.github.xgl34222220.luoshu.ui.studio.FontStudioUiState
import io.github.xgl34222220.luoshu.ui.studio.StudioProfile
import io.github.xgl34222220.luoshu.ui.studio.applyStudioProfile
import io.github.xgl34222220.luoshu.ui.studio.encodeStudioProfile
import io.github.xgl34222220.luoshu.ui.studio.parseStudioProfile
import java.io.BufferedReader
import java.io.InputStreamReader
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val LIBRARY_BACKUP_SCHEMA = 1
private const val LIBRARY_BACKUP_TYPE = "luoshu-font-library-backup"
private const val LIBRARY_BACKUP_MAX_CHARS = 1_048_576

internal enum class FontMigrationSeverity {
    READY,
    WARNING,
    BLOCKER,
}

@Immutable
internal data class FontMigrationCheck(
    val id: String,
    val title: String,
    val detail: String,
    val severity: FontMigrationSeverity,
    val repairable: Boolean = false,
)

@Immutable
internal data class FontMigrationReport(
    val checks: List<FontMigrationCheck>,
) {
    val blockerCount: Int get() = checks.count { it.severity == FontMigrationSeverity.BLOCKER }
    val warningCount: Int get() = checks.count { it.severity == FontMigrationSeverity.WARNING }
    val ready: Boolean get() = blockerCount == 0
}

@Immutable
internal data class FontLibraryBackupParseResult(
    val collections: FontLibraryCollections? = null,
    val profile: StudioProfile? = null,
    val errors: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
) {
    val valid: Boolean get() = collections != null && errors.isEmpty()
}

internal fun pruneFontLibraryCollections(
    collections: FontLibraryCollections,
    availableIds: Set<String>,
): FontLibraryCollections = FontLibraryCollections(
    favoriteIds = collections.favoriteIds.intersect(availableIds),
    tags = collections.tags
        .filterKeys { it in availableIds }
        .mapValues { (_, values) -> values.intersect(fontLibraryTagOptions.toSet()) }
        .filterValues { it.isNotEmpty() },
)

internal fun buildFontMigrationReport(
    fonts: List<FontItem>,
    collections: FontLibraryCollections,
    studioState: FontStudioUiState,
    watchConfigured: Boolean,
    watchPermission: Boolean,
): FontMigrationReport {
    val availableIds = fonts.map { it.id }.toSet()
    val staleFavorites = collections.favoriteIds - availableIds
    val staleTagIds = collections.tags.keys - availableIds
    val staleCount = (staleFavorites + staleTagIds).size
    val invalidCount = fonts.count { !it.valid }
    val selected = studioState.slots.mapNotNull { it.font }
    val selectedValid = selected.size == studioState.slots.size && selected.all { it.valid }
    val conflicts = analyzeFontLibraryConflicts(fonts)

    val checks = buildList {
        add(
            FontMigrationCheck(
                id = "library",
                title = "字体库可读取",
                detail = if (fonts.isEmpty()) "当前没有可迁移的字体 Family" else "已读取 ${fonts.size} 个 Family",
                severity = if (fonts.isEmpty()) FontMigrationSeverity.BLOCKER else FontMigrationSeverity.READY,
            ),
        )
        add(
            FontMigrationCheck(
                id = "collections",
                title = "收藏与标签引用",
                detail = if (staleCount == 0) "收藏和标签均指向当前字体库" else "发现 $staleCount 个已失效 Family 引用，可安全清理",
                severity = if (staleCount == 0) FontMigrationSeverity.READY else FontMigrationSeverity.WARNING,
                repairable = staleCount > 0,
            ),
        )
        add(
            FontMigrationCheck(
                id = "studio",
                title = "组合方案完整性",
                detail = if (selectedValid) "中文、英文和数字槽位均已选择有效字体" else "组合方案存在缺失或未通过验证的槽位",
                severity = if (selectedValid) FontMigrationSeverity.READY else FontMigrationSeverity.BLOCKER,
            ),
        )
        add(
            FontMigrationCheck(
                id = "invalid",
                title = "无效字体隔离",
                detail = if (invalidCount == 0) "当前字体均通过基础验证" else "$invalidCount 个字体需要检查，升级不会自动删除",
                severity = if (invalidCount == 0) FontMigrationSeverity.READY else FontMigrationSeverity.WARNING,
            ),
        )
        add(
            FontMigrationCheck(
                id = "conflicts",
                title = "重复与命名冲突",
                detail = if (conflicts.issueIds.isEmpty()) "未发现明显的重复或命名冲突" else "发现 ${conflicts.issueIds.size} 个整理提示，需通过 SHA-256 最终确认",
                severity = if (conflicts.issueIds.isEmpty()) FontMigrationSeverity.READY else FontMigrationSeverity.WARNING,
            ),
        )
        if (watchConfigured) {
            add(
                FontMigrationCheck(
                    id = "watch",
                    title = "SAF 目录权限",
                    detail = if (watchPermission) "监视目录读取权限仍有效" else "监视目录权限已失效，升级后需要重新选择目录",
                    severity = if (watchPermission) FontMigrationSeverity.READY else FontMigrationSeverity.WARNING,
                ),
            )
        }
    }
    return FontMigrationReport(checks)
}

internal fun encodeFontLibraryBackup(
    collections: FontLibraryCollections,
    studioState: FontStudioUiState,
    fonts: List<FontItem>,
): String {
    val collectionsObject = JSONObject()
        .put("favorites", JSONArray(collections.favoriteIds.sorted()))
        .put(
            "tags",
            JSONObject().apply {
                collections.tags.toSortedMap().forEach { (fontId, values) ->
                    put(fontId, JSONArray(values.filter { it in fontLibraryTagOptions }.sorted()))
                }
            },
        )
    val inventory = JSONArray().apply {
        fonts.sortedBy { it.id }.forEach { font ->
            put(JSONObject().put("id", font.id).put("name", font.name).put("valid", font.valid))
        }
    }
    return JSONObject()
        .put("schema", LIBRARY_BACKUP_SCHEMA)
        .put("type", LIBRARY_BACKUP_TYPE)
        .put("appVersion", BuildConfig.VERSION_NAME)
        .put("createdAt", LocalDateTime.now().toString())
        .put("collections", collectionsObject)
        .put("studioProfile", JSONObject(encodeStudioProfile(studioState)))
        .put("fontInventory", inventory)
        .put("includesFontFiles", false)
        .toString(2)
}

internal fun parseFontLibraryBackup(
    raw: String,
    availableFonts: List<FontItem>,
): FontLibraryBackupParseResult {
    val errors = mutableListOf<String>()
    val warnings = mutableListOf<String>()
    val root = runCatching { JSONObject(raw) }.getOrElse {
        return FontLibraryBackupParseResult(errors = listOf("JSON 格式无效：${it.message ?: "无法解析"}"))
    }
    if (root.optInt("schema", -1) != LIBRARY_BACKUP_SCHEMA) errors += "不支持的备份版本"
    if (root.optString("type") != LIBRARY_BACKUP_TYPE) errors += "这不是洛书字体库备份"
    val collectionsObject = root.optJSONObject("collections")
    if (collectionsObject == null) errors += "备份缺少收藏与标签配置"
    if (errors.isNotEmpty() || collectionsObject == null) {
        return FontLibraryBackupParseResult(errors = errors.distinct())
    }

    val availableIds = availableFonts.map { it.id }.toSet()
    val favoritesArray = collectionsObject.optJSONArray("favorites") ?: JSONArray()
    val requestedFavorites = buildSet {
        for (index in 0 until favoritesArray.length()) {
            favoritesArray.optString(index).trim().takeIf { it.isNotBlank() }?.let(::add)
        }
    }
    val tagsObject = collectionsObject.optJSONObject("tags") ?: JSONObject()
    val requestedTags = buildMap {
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
    val requested = FontLibraryCollections(requestedFavorites, requestedTags)
    val collections = pruneFontLibraryCollections(requested, availableIds)
    val missingIds = (requested.favoriteIds + requested.tags.keys) - availableIds
    if (missingIds.isNotEmpty()) warnings += "本机缺少 ${missingIds.size} 个 Family，相关收藏和标签已跳过"

    val profileObject = root.optJSONObject("studioProfile")
    val profileResult = if (profileObject == null) null else parseStudioProfile(profileObject.toString(), availableFonts)
    val profile = profileResult?.profile?.takeIf { profileResult.valid }
    if (profileObject == null) {
        warnings += "备份没有组合方案"
    } else if (profile == null) {
        warnings += "组合方案未恢复：${profileResult?.errors?.joinToString("；").orEmpty().ifBlank { "配置无效" }}"
    }
    warnings += profileResult?.warnings.orEmpty()
    if (root.optBoolean("includesFontFiles", false)) {
        warnings += "当前版本只恢复配置，不会从 JSON 写入字体二进制"
    }

    return FontLibraryBackupParseResult(
        collections = collections,
        profile = profile,
        warnings = warnings.distinct(),
    )
}

@Composable
internal fun FontLibraryUtilitiesBar(
    style: UiStyle,
    fonts: List<FontItem>,
    collections: FontLibraryCollections,
    studioState: FontStudioUiState,
    studioActions: FontStudioActions,
    enabled: Boolean,
    onCollectionsChange: (FontLibraryCollections) -> Unit,
) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FontDirectoryMonitorTool(
            style = style,
            enabled = enabled,
            modifier = Modifier.weight(1f),
        )
        FontLibraryBackupTool(
            style = style,
            fonts = fonts,
            collections = collections,
            studioState = studioState,
            studioActions = studioActions,
            enabled = enabled,
            onCollectionsChange = onCollectionsChange,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun FontLibraryBackupTool(
    style: UiStyle,
    fonts: List<FontItem>,
    collections: FontLibraryCollections,
    studioState: FontStudioUiState,
    studioActions: FontStudioActions,
    enabled: Boolean,
    onCollectionsChange: (FontLibraryCollections) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var showDialog by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf("") }
    var pending by remember { mutableStateOf<FontLibraryBackupParseResult?>(null) }
    val watchStore = remember(context.applicationContext) { FontDirectoryWatchStore(context.applicationContext) }
    val watchConfig = remember(showDialog) { watchStore.load() }
    val migration = remember(fonts, collections, studioState, watchConfig, showDialog) {
        buildFontMigrationReport(
            fonts = fonts,
            collections = collections,
            studioState = studioState,
            watchConfigured = watchConfig.configured,
            watchPermission = hasPersistedFontDirectoryPermission(context, watchConfig),
        )
    }

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json"),
    ) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val result = runCatching {
                withContext(Dispatchers.IO) {
                    context.contentResolver.openOutputStream(uri, "wt")?.bufferedWriter()?.use { writer ->
                        writer.write(encodeFontLibraryBackup(collections, studioState, fonts))
                    } ?: error("无法打开目标文件")
                }
            }
            errorMessage = result.exceptionOrNull()?.message.orEmpty()
            status = if (result.isSuccess) "字体库配置备份已导出" else ""
        }
    }
    val importLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val result = runCatching {
                withContext(Dispatchers.IO) { readBackupText(context.contentResolver, uri) }
            }.mapCatching { raw -> parseFontLibraryBackup(raw, fonts) }
            val parsed = result.getOrNull()
            when {
                result.isFailure -> {
                    pending = null
                    status = ""
                    errorMessage = result.exceptionOrNull()?.message ?: "备份读取失败"
                }
                parsed == null || !parsed.valid -> {
                    pending = null
                    status = ""
                    errorMessage = parsed?.errors?.joinToString("\n") ?: "备份读取失败"
                }
                else -> {
                    pending = parsed
                    errorMessage = ""
                    status = buildString {
                        append("备份可恢复：收藏 ${parsed.collections?.favoriteIds?.size ?: 0} 项")
                        if (parsed.profile != null) append(" · 含组合方案")
                        if (parsed.warnings.isNotEmpty()) append("\n${parsed.warnings.joinToString("\n")}")
                    }
                }
            }
        }
    }

    Surface(
        onClick = { showDialog = true },
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 22.dp else 19.dp),
        color = MaterialTheme.colorScheme.tertiaryContainer,
        contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(Icons.Rounded.Description, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.size(8.dp))
            Column(Modifier.weight(1f)) {
                Text("备份与升级检查", fontSize = 11.sp, fontWeight = FontWeight.Black)
                Text(
                    if (migration.ready) "阻断 0 · 提示 ${migration.warningCount}" else "阻断 ${migration.blockerCount} · 提示 ${migration.warningCount}",
                    fontSize = 9.sp,
                    color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = .72f),
                )
            }
        }
    }

    if (showDialog) {
        AlertDialog(
            onDismissRequest = { showDialog = false },
            shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 34.dp else 28.dp),
            icon = {
                Icon(
                    if (migration.ready) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                    contentDescription = null,
                    tint = if (migration.ready) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                )
            },
            title = { Text("字体库备份与升级检查", fontWeight = FontWeight.Black) },
            text = {
                Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text(
                        "JSON 备份包含收藏、标签与组合方案，不包含字体二进制文件。恢复前会按本机 Family ID 校验。",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 10.sp,
                    )
                    migration.checks.forEach { check ->
                        MigrationCheckRow(check)
                    }
                    if (migration.checks.any { it.repairable }) {
                        OutlinedButton(
                            onClick = {
                                onCollectionsChange(pruneFontLibraryCollections(collections, fonts.map { it.id }.toSet()))
                                status = "已清理失效的收藏与标签引用"
                            },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Icon(Icons.Rounded.Refresh, contentDescription = null, modifier = Modifier.size(17.dp))
                            Spacer(Modifier.size(6.dp))
                            Text("修复可安全迁移项")
                        }
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = { importLauncher.launch(arrayOf("application/json", "text/plain")) },
                            modifier = Modifier.weight(1f),
                        ) {
                            Icon(Icons.Rounded.FileUpload, contentDescription = null, modifier = Modifier.size(17.dp))
                            Spacer(Modifier.size(5.dp))
                            Text("恢复")
                        }
                        OutlinedButton(
                            onClick = { exportLauncher.launch(backupFileName()) },
                            modifier = Modifier.weight(1f),
                        ) {
                            Icon(Icons.Rounded.FileDownload, contentDescription = null, modifier = Modifier.size(17.dp))
                            Spacer(Modifier.size(5.dp))
                            Text("备份")
                        }
                    }
                    if (status.isNotBlank()) {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.primaryContainer,
                        ) {
                            Text(status, modifier = Modifier.padding(10.dp), fontSize = 10.sp)
                        }
                    }
                    if (errorMessage.isNotBlank()) {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(16.dp),
                            color = MaterialTheme.colorScheme.errorContainer,
                        ) {
                            Text(errorMessage, modifier = Modifier.padding(10.dp), fontSize = 10.sp)
                        }
                    }
                }
            },
            confirmButton = {
                val parsed = pending
                if (parsed != null) {
                    TextButton(
                        onClick = {
                            parsed.collections?.let(onCollectionsChange)
                            parsed.profile?.let { applyStudioProfile(it, studioActions) }
                            pending = null
                            status = if (parsed.profile != null) {
                                "收藏、标签和组合方案已恢复；生成前仍可继续调整"
                            } else {
                                "收藏和标签已恢复；组合方案因缺失 Family 未写入"
                            }
                        },
                    ) { Text("确认恢复", fontWeight = FontWeight.Black) }
                } else {
                    TextButton(onClick = { showDialog = false }) { Text("完成") }
                }
            },
            dismissButton = {
                if (pending != null) {
                    TextButton(onClick = { pending = null; status = "" }) { Text("取消恢复") }
                }
            },
        )
    }
}

@Composable
private fun MigrationCheckRow(check: FontMigrationCheck) {
    val color = when (check.severity) {
        FontMigrationSeverity.READY -> MaterialTheme.colorScheme.primary
        FontMigrationSeverity.WARNING -> MaterialTheme.colorScheme.tertiary
        FontMigrationSeverity.BLOCKER -> MaterialTheme.colorScheme.error
    }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = color.copy(alpha = .10f),
    ) {
        Row(Modifier.padding(9.dp), verticalAlignment = Alignment.Top) {
            Icon(
                if (check.severity == FontMigrationSeverity.READY) Icons.Rounded.CheckCircle else Icons.Rounded.Warning,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(19.dp),
            )
            Spacer(Modifier.size(7.dp))
            Column(Modifier.weight(1f)) {
                Text(check.title, fontSize = 10.sp, fontWeight = FontWeight.Black)
                Text(check.detail, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp, lineHeight = 13.sp)
            }
        }
    }
}

private fun readBackupText(contentResolver: ContentResolver, uri: Uri): String {
    contentResolver.openInputStream(uri)?.use { input ->
        BufferedReader(InputStreamReader(input, Charsets.UTF_8)).use { reader ->
            val output = StringBuilder()
            val buffer = CharArray(4096)
            while (true) {
                val count = reader.read(buffer)
                if (count < 0) break
                output.append(buffer, 0, count)
                if (output.length > LIBRARY_BACKUP_MAX_CHARS) error("备份文件超过 1 MB 限制")
            }
            return output.toString()
        }
    }
    error("无法打开备份文件")
}

private fun backupFileName(): String {
    val timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"))
    return "LuoShu-library-backup-$timestamp.json"
}
