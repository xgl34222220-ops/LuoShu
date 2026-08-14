package io.github.xgl34222220.luoshu.ui.settings

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Backup
import androidx.compose.material.icons.rounded.FileDownload
import androidx.compose.material.icons.rounded.FileUpload
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import io.github.xgl34222220.luoshu.RootShell
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.library.FontLibraryCollectionStore
import io.github.xgl34222220.luoshu.ui.library.FontLibraryCollections
import io.github.xgl34222220.luoshu.ui.studio.StudioPresetStore
import io.github.xgl34222220.luoshu.ui.studio.StudioProfileBridgeStore
import io.github.xgl34222220.luoshu.ui.studio.decodePresets
import io.github.xgl34222220.luoshu.ui.studio.encodePresets
import java.io.File
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val FULL_BACKUP_TYPE = "luoshu-full-backup"
private const val FULL_BACKUP_SCHEMA = 1
private const val FULL_BACKUP_ROOT_TOOL = "/data/adb/modules/LuoShu/system/bin/luoshu-backup"
private const val FULL_BACKUP_MAX_FILES = 1200
private const val FULL_BACKUP_MAX_BYTES = 1_825_361_920L

@Composable
internal fun FullBackupCard(
    settings: AppearanceSettings,
    appearanceActions: AppearanceActions,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pendingExportRoot by remember { mutableStateOf<File?>(null) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }

    val exportLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri: Uri? ->
        val stage = pendingExportRoot
        pendingExportRoot = null
        if (uri == null || stage == null) { stage?.deleteRecursively(); return@rememberLauncherForActivityResult }
        scope.launch {
            busy = true; message = ""; error = ""
            val result = runCatching { withContext(Dispatchers.IO) { writeFullBackup(context, uri, stage) } }
            stage.deleteRecursively()
            busy = false
            if (result.isSuccess) message = result.getOrThrow() else error = result.exceptionOrNull()?.message ?: "备份导出失败"
        }
    }
    val importLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            busy = true; message = ""; error = ""
            val result = runCatching { restoreFullBackup(context, uri, appearanceActions) }
            busy = false
            if (result.isSuccess) message = result.getOrThrow() else error = result.exceptionOrNull()?.message ?: "备份恢复失败"
        }
    }

    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
      Column(Modifier.fillMaxWidth().padding(16.dp)) {
        Text("完整备份与恢复", fontSize = 17.sp, fontWeight = FontWeight.Black)
        Spacer(Modifier.size(5.dp))
        Text(
            "导出 .luoshu.zip：用户字体文件、收藏/标签、字体方案、当前 Studio 组合、外观设置和可迁移洛书配置。每个文件都会写入 SHA-256 清单。",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 10.sp,
            lineHeight = 15.sp,
        )
        Spacer(Modifier.size(10.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    scope.launch {
                        busy = true; message = ""; error = ""
                        val stage = File(context.cacheDir, "full_backup/export-${UUID.randomUUID()}")
                        val result = runCatching { prepareFullBackupStage(context, stage, settings) }
                        busy = false
                        if (result.isSuccess) {
                            pendingExportRoot = stage
                            exportLauncher.launch(fullBackupFileName())
                        } else {
                            stage.deleteRecursively()
                            error = result.exceptionOrNull()?.message ?: "无法准备备份"
                        }
                    }
                },
                enabled = !busy,
                modifier = Modifier.weight(1f),
            ) {
                Icon(Icons.Rounded.FileDownload, null, Modifier.size(17.dp)); Spacer(Modifier.width(5.dp)); Text("导出完整备份")
            }
            OutlinedButton(
                onClick = { importLauncher.launch(arrayOf("application/zip", "application/octet-stream")) },
                enabled = !busy,
                modifier = Modifier.weight(1f),
            ) {
                Icon(Icons.Rounded.FileUpload, null, Modifier.size(17.dp)); Spacer(Modifier.width(5.dp)); Text("恢复备份")
            }
        }
        if (busy) Row(Modifier.fillMaxWidth().padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp); Spacer(Modifier.width(8.dp)); Text("正在校验和处理备份…", fontSize = 10.sp)
        }
        if (message.isNotBlank()) Text(message, color = MaterialTheme.colorScheme.primary, fontSize = 10.sp, modifier = Modifier.padding(top = 8.dp))
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error, fontSize = 10.sp, modifier = Modifier.padding(top = 8.dp))
        Spacer(Modifier.size(8.dp))
        Surface(Modifier.fillMaxWidth(), RoundedCornerShape(16.dp), color = MaterialTheme.colorScheme.primary.copy(alpha = .07f)) {
            Row(Modifier.padding(10.dp), verticalAlignment = Alignment.Top) {
                Icon(Icons.Rounded.Backup, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(7.dp))
                Text("恢复不会复制旧设备的锁、运行中任务、缓存或系统字体 payload，也不会强制把旧机当前字体立即设为新机当前字体。", fontSize = 9.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
          }
    }
}

private suspend fun prepareFullBackupStage(context: Context, stage: File, settings: AppearanceSettings) {
    withContext(Dispatchers.IO) { stage.deleteRecursively(); stage.mkdirs(); File(stage, "app").mkdirs() }
    val root = RootShell.exec(
        "sh ${RootShell.quote(FULL_BACKUP_ROOT_TOOL)} export-root ${RootShell.quote(stage.absolutePath)}",
        timeoutMs = 180_000L,
    )
    require(root.code == 0 && root.stdout.contains("\"status\":\"ok\"")) { root.stderr.ifBlank { "字体文件暂存失败" } }

    val collections = FontLibraryCollectionStore(context).load()
    val presets = StudioPresetStore(context).list()
    val profile = StudioProfileBridgeStore(context).loadCurrent()
    val state = JSONObject()
        .put("appearance", encodeAppearance(settings))
        .put("collections", encodeCollections(collections))
        .put("presets", JSONObject(encodePresets(presets)))
        .put("studioProfile", profile.takeIf { it.isNotBlank() }?.let(::JSONObject) ?: JSONObject.NULL)
    withContext(Dispatchers.IO) { File(stage, "app/state.json").writeText(state.toString(2), Charsets.UTF_8) }
    writeManifest(stage)
}

private fun writeFullBackup(context: Context, uri: Uri, stage: File): String {
    val output = context.contentResolver.openOutputStream(uri, "w") ?: error("无法打开备份目标")
    ZipOutputStream(output.buffered()).use { zip ->
        stage.walkTopDown().filter { it.isFile }.sortedBy { it.relativeTo(stage).invariantSeparatorsPath }.forEach { file ->
            val relative = file.relativeTo(stage).invariantSeparatorsPath
            zip.putNextEntry(ZipEntry(relative))
            file.inputStream().buffered().use { it.copyTo(zip) }
            zip.closeEntry()
        }
    }
    return "完整备份已导出"
}

private suspend fun restoreFullBackup(context: Context, uri: Uri, actions: AppearanceActions): String {
    val stage = File(context.cacheDir, "full_backup/restore-${UUID.randomUUID()}")
    return try {
        withContext(Dispatchers.IO) { extractBackupSecurely(context, uri, stage); validateManifest(stage) }
        val appState = withContext(Dispatchers.IO) { JSONObject(File(stage, "app/state.json").readText(Charsets.UTF_8)) }
        val root = RootShell.exec(
            "sh ${RootShell.quote(FULL_BACKUP_ROOT_TOOL)} restore-root ${RootShell.quote(stage.absolutePath)}",
            timeoutMs = 180_000L,
        )
        require(root.code == 0 && root.stdout.contains("\"status\":\"ok\"")) { root.stderr.ifBlank { "字体文件恢复失败" } }

        appState.optJSONObject("collections")?.let { FontLibraryCollectionStore(context).save(decodeCollections(it)) }
        appState.optJSONObject("presets")?.let { StudioPresetStore(context).replaceAll(decodePresets(it.toString())) }
        appState.optJSONObject("studioProfile")?.let { StudioProfileBridgeStore(context).saveCurrent(it.toString()) }
        appState.optJSONObject("appearance")?.let { restoreAppearance(it, actions) }
        "备份已恢复；请重新进入字体库检查字体，并按需重新应用方案"
    } finally {
        withContext(Dispatchers.IO) { stage.deleteRecursively() }
    }
}

private fun writeManifest(stage: File) {
    val files = JSONArray()
    var total = 0L
    stage.walkTopDown().filter { it.isFile && it.name != "manifest.json" }.sortedBy { it.relativeTo(stage).invariantSeparatorsPath }.forEach { file ->
        val relative = file.relativeTo(stage).invariantSeparatorsPath
        total += file.length()
        require(total <= FULL_BACKUP_MAX_BYTES) { "备份内容超过大小限制" }
        files.put(JSONObject().put("path", relative).put("bytes", file.length()).put("sha256", sha256(file)))
    }
    require(files.length() <= FULL_BACKUP_MAX_FILES) { "备份文件数量过多" }
    val manifest = JSONObject()
        .put("schema", FULL_BACKUP_SCHEMA)
        .put("type", FULL_BACKUP_TYPE)
        .put("appVersion", BuildConfig.VERSION_NAME)
        .put("createdAt", System.currentTimeMillis())
        .put("fileCount", files.length())
        .put("totalBytes", total)
        .put("files", files)
    File(stage, "manifest.json").writeText(manifest.toString(2), Charsets.UTF_8)
}

private fun validateManifest(stage: File) {
    val manifestFile = File(stage, "manifest.json")
    require(manifestFile.isFile) { "备份缺少 manifest.json" }
    val root = JSONObject(manifestFile.readText(Charsets.UTF_8))
    require(root.optInt("schema", -1) == FULL_BACKUP_SCHEMA && root.optString("type") == FULL_BACKUP_TYPE) { "不是受支持的洛书完整备份" }
    val files = root.optJSONArray("files") ?: error("备份清单不完整")
    require(files.length() <= FULL_BACKUP_MAX_FILES) { "备份文件数量异常" }
    var total = 0L
    for (index in 0 until files.length()) {
        val item = files.getJSONObject(index)
        val relative = safeRelativePath(item.getString("path"))
        val file = File(stage, relative)
        require(file.isFile) { "备份缺少文件：$relative" }
        val bytes = item.optLong("bytes", -1L)
        require(bytes >= 0 && file.length() == bytes) { "文件大小校验失败：$relative" }
        total += bytes
        require(total <= FULL_BACKUP_MAX_BYTES) { "备份展开后超过大小限制" }
        require(sha256(file).equals(item.getString("sha256"), ignoreCase = true)) { "SHA-256 校验失败：$relative" }
    }
    require(File(stage, "app/state.json").isFile) { "备份缺少 App 配置" }
}

private fun extractBackupSecurely(context: Context, uri: Uri, stage: File) {
    stage.deleteRecursively(); stage.mkdirs()
    val input = context.contentResolver.openInputStream(uri) ?: error("无法打开备份文件")
    var count = 0; var total = 0L
    ZipInputStream(input.buffered()).use { zip ->
        while (true) {
            val entry = zip.nextEntry ?: break
            count += 1; require(count <= FULL_BACKUP_MAX_FILES + 1) { "备份条目过多" }
            val relative = safeRelativePath(entry.name)
            val target = File(stage, relative)
            require(target.canonicalPath.startsWith(stage.canonicalPath + File.separator)) { "非法备份路径" }
            if (entry.isDirectory) target.mkdirs() else {
                target.parentFile?.mkdirs()
                target.outputStream().buffered().use { out ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = zip.read(buffer); if (read < 0) break
                        total += read; require(total <= FULL_BACKUP_MAX_BYTES) { "备份展开后超过大小限制" }
                        out.write(buffer, 0, read)
                    }
                }
            }
            zip.closeEntry()
        }
    }
}

private fun safeRelativePath(value: String): String {
    val normalized = value.replace('\\', '/').trimStart('/')
    require(normalized.isNotBlank() && normalized.length <= 240) { "非法备份路径" }
    require(normalized.split('/').none { it.isBlank() || it == "." || it == ".." }) { "非法备份路径" }
    return normalized
}

private fun encodeAppearance(settings: AppearanceSettings) = JSONObject()
    .put("uiStyle", settings.uiStyle.name).put("themeMode", settings.themeMode.name)
    .put("seedArgb", settings.seedArgb).put("kolorStyle", settings.kolorStyle.name)
    .put("monetEnabled", settings.monetEnabled).put("amoledBlack", settings.amoledBlack)
    .put("blurEnabled", settings.blurEnabled).put("glassEnabled", settings.glassEnabled)
    .put("floatingDock", settings.floatingDock).put("highRefreshRate", settings.highRefreshRate)

private fun restoreAppearance(root: JSONObject, actions: AppearanceActions) {
    runCatching { actions.setUiStyle(UiStyle.valueOf(root.optString("uiStyle"))) }
    runCatching { actions.setThemeMode(ThemeMode.valueOf(root.optString("themeMode"))) }
    if (root.has("seedArgb")) actions.setSeedArgb(root.optInt("seedArgb"))
    runCatching { actions.setKolorStyle(KolorStyle.valueOf(root.optString("kolorStyle"))) }
    actions.setMonetEnabled(root.optBoolean("monetEnabled", true)); actions.setAmoledBlack(root.optBoolean("amoledBlack", false))
    actions.setGlassEnabled(root.optBoolean("glassEnabled", true)); actions.setBlurEnabled(root.optBoolean("blurEnabled", true))
    actions.setFloatingDock(root.optBoolean("floatingDock", true)); actions.setHighRefreshRate(root.optBoolean("highRefreshRate", false))
}

private fun encodeCollections(value: FontLibraryCollections) = JSONObject()
    .put("favorites", JSONArray(value.favoriteIds.sorted()))
    .put("tags", JSONObject().apply { value.tags.toSortedMap().forEach { (id, tags) -> put(id, JSONArray(tags.sorted())) } })

private fun decodeCollections(root: JSONObject): FontLibraryCollections {
    val favorites = buildSet { val a = root.optJSONArray("favorites") ?: JSONArray(); for (i in 0 until a.length()) a.optString(i).takeIf { it.isNotBlank() }?.let(::add) }
    val tagsRoot = root.optJSONObject("tags") ?: JSONObject()
    val tags = buildMap<String, Set<String>> { val keys = tagsRoot.keys(); while (keys.hasNext()) { val id = keys.next(); val a = tagsRoot.optJSONArray(id) ?: continue; val values = buildSet { for (i in 0 until a.length()) a.optString(i).takeIf { it.isNotBlank() }?.let(::add) }; if (values.isNotEmpty()) put(id, values) } }
    return FontLibraryCollections(favorites, tags)
}

private fun sha256(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().buffered().use { input -> val buffer = ByteArray(64 * 1024); while (true) { val read = input.read(buffer); if (read < 0) break; digest.update(buffer, 0, read) } }
    return digest.digest().joinToString("") { "%02x".format(it) }
}

private fun fullBackupFileName(): String = "LuoShu-Backup-${SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())}.luoshu.zip"
